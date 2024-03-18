"""
take a csv in the format of:
	('DISPLAY_NAME, SUBTITLE_3, COLORIZATION_FILE_NAME, BANNER_MAIN_IMG, 
	SALE_SWATCH, DISPLAY_NAME_1, CATEGORY2, SUBTITLE_3_1, 
	COLORIZATION_FILE_NAME_1, BANNER_MAIN_IMG_1')
Create colorization filenames where they don't exist
Carry over lifestyles as needed w/ appropriate name
Output an import doc for BCC upload

 """
CSV = None
BCC_IMPORT_DOC = None
catids_added_tobcc_data = []
uploaded_files = []

import sys, threading, ftplib, requests, io, time, json, hashlib, re, os
import datetime
from PIL import Image

def check_file_exists_ftp(name):
	server = "s7ftp1.scene7.com"
	user_name = "rhis"
	password = "G1cO2@Me3N!"
	try:
		ftp = ftplib.FTP(host = server, user = user_name, passwd = password)
	except TimeoutError:
		time.sleep(15)
		ftp = ftplib.FTP(host = server, user = user_name, passwd = password)
	ftp.cwd('automated_uploads')
	files = ftp.nlst()
	# ftp.quit()
	if name+'.png' in files: return True
	else: return False


def upload_to_ftp(binary, name):
	server = "s7ftp1.scene7.com"
	user_name = "rhis"
	password = "G1cO2@Me3N!"
	try:
		ftp = ftplib.FTP(host = server, user = user_name, passwd = password)
	except TimeoutError:
		time.sleep(15)
		ftp = ftplib.FTP(host = server, user = user_name, passwd = password)
	ftp.cwd('automated_uploads')
	binary.seek(0)
	try:
		ftp.storbinary(f"STOR {name}.png", fp = binary) 
	except BrokenPipeError:
		upload_to_ftp(binary, name)
	return None

def download(file):
	try:
		response = requests.get(f'https://media.restorationhardware.com/is/image/rhis/{file}?req=imageprops,json')
		if response.status_code > 300:
			return
		data_json = response.text.split("(", 1)[1].strip(")").strip(",\"\");")
		data_dict = json.loads(data_json)
		height = (data_dict['image.height'])
		width = (data_dict['image.width'])
		#print(width,height)

		if int(width) > 4000:
			height = round(int(height) * (4000/int(width)))
			width = 4000
			#print(width,height)

		download_url = f'https://media.restorationhardware.com/is/image/rhis/{file}?wid={width}&hei={height}&fmt=png-alpha'
		image_data = requests.get(download_url)
		im = Image.open(io.BytesIO(image_data.content))
		return im
		# im.save(f'{destination}{file}_RHR.png')
	except (KeyError, ConnectionError) as err:
		return None

def cleanup_banner_img_name(data):
	# take a banner main image and remove the extra crap
	#/is/image/rhis/cat7760026?wid=696&fmt=jpeg&qlt=90,0&op_sharpen=0&resMode=sharp&op_usm=0.6,1.0,5,0&iccEmbed=1
	#remove everything before the '/'
	# remove everything after the '?'
	data = re.sub(r'.*\/','',data)
	data = re.sub(r'\?.*','',data)
	return data

def image_exists(img_name: str) -> bool:
	'''request if the image exists from dynamic Media Classic'''
	response = requests.get(f'https://media.restorationhardware.com/is/image/rhis/{img_name}?req=exists,json')
	if '"catalogRecord.exists":"0"' in response.text:
		return False
	return True

def transfer_file(file_data:tuple) -> None:
	'''
	Take a tuple in the format of (donor_file, recipient_name)
	and upload to FTP
	'''
	originating_name = file_data[0]
	# process both RHR and non-RHR
	original_file = download(originating_name)
	if original_file == None: 
		return
	new_name = file_data[1]
	output = io.BytesIO()
	original_file.save(output, format = "PNG")
	upload_to_ftp(output, new_name)

def setup_import_doc() -> str:
	'''
	setup a csv on the desktop w/ the appropriate headers
	'''
	time_stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
	loc = os.path.expanduser(f'~/Desktop/BCC_Import_for_CG_Colorization{time_stamp}.csv')
	with open(loc,'a') as csv:
		csv.write('/atg/commerce/catalog/ProductCatalog:category,,,,LOCALE=en_US\nID,colorizable,colorizationFileName,colorizeType,disableDynamicColorization\n')
	return loc

def process_line(line):
	if line[0] == 'DISPLAY_NAME': return
	# determine if the swatch is in the shown-in copy for the CG
	# if it's not, return
	if len(line) < 8: return
	if not line[7].replace('Shown In ',"") in line[5]: return
	#determine which image to use - it's either the category ID or the cleaned up version of the Banner Main Image
	banner_main_image = cleanup_banner_img_name(line[8])
	donor_image = None
	if banner_main_image != '' and image_exists(banner_main_image):
		donor_image = banner_main_image
	elif image_exists(line[6]):
		donor_image = line[6]
	else:
		# need to handle neither image existing 
		return
	colorization_filename = hashlib.shake_128(line[0].encode()).hexdigest(4)
	recipient_filename = f'{colorization_filename}_cl{line[4]}'
	if recipient_filename in uploaded_files or image_exists(recipient_filename):
		return
	# while threading.active_count() > 50: continue
	threading.Thread(target = transfer_file, args = ((donor_image, recipient_filename),)).start()
	uploaded_files.append(recipient_filename)
	# transfer_file((donor_image, recipient_filename))
	with open(BCC_IMPORT_DOC, 'a') as bcc_csv:
		if line[6] not in catids_added_tobcc_data:
			bcc_csv.write(f'{line[6]},true,{colorization_filename},static-color,false\n')
			catids_added_tobcc_data.append(line[6])

def main():
	global CSV
	global BCC_IMPORT_DOC
	global catids_added_tobcc_data
	global uploaded_files
	if len(sys.argv) != 2: 
		print(f'Incorrect arguments. Expected 1 got {len(sys.argv)-1}')
		return
	CSV = sys.argv[1]
	# CSV = '/Users/landerson2/Desktop/total_site_static_color.csv'
	BCC_IMPORT_DOC = setup_import_doc()
	catids_added_tobcc_data = []
	uploaded_files = []
	with open(CSV, 'r') as csv_file:
		for _ in csv_file.readlines():
			
			line = _.replace('''"''',"").split(',')
			threading.Thread(target = process_line, args = (line,)).start()
			while threading.active_count() > 50: continue
			# if line[0] == 'DISPLAY_NAME': continue
			# # determine if the swatch is in the shown-in copy for the CG
			# # if it's not, continue
			# if len(line) < 8: continue
			# if not line[7].replace('Shown In ',"") in line[5]: continue
			# #determine which image to use - it's either the category ID or the cleaned up version of the Banner Main Image
			# banner_main_image = cleanup_banner_img_name(line[8])
			# donor_image = None
			# if banner_main_image != '' and image_exists(banner_main_image):
			# 	donor_image = banner_main_image
			# elif image_exists(line[6]):
			# 	donor_image = line[6]
			# else:
			# 	# need to handle neither image existing 
			# 	continue
			# colorization_filename = hashlib.shake_128(line[0].encode()).hexdigest(4)
			# recipient_filename = f'{colorization_filename}_cl{line[4]}'
			# if recipient_filename in uploaded_files or image_exists(recipient_filename):
			# 	continue
			# while threading.active_count() > 50: continue
			# threading.Thread(target = transfer_file, args = ((donor_image, recipient_filename),)).start()
			# uploaded_files.append(recipient_filename)
			# # transfer_file((donor_image, recipient_filename))
			# with open(BCC_IMPORT_DOC, 'a') as bcc_csv:
			# 	if line[6] not in catids_added_tobcc_data:
			# 		bcc_csv.write(f'{line[6]},true,{colorization_filename},static-color\n')
			# 		catids_added_tobcc_data.append(line[6])

main()