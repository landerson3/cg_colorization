"""
take a csv in the format of:
	('DISPLAY_NAME, SUBTITLE_3, COLORIZATION_FILE_NAME, BANNER_MAIN_IMG, 
	SALE_SWATCH, DISPLAY_NAME_1, CATEGORY2, SUBTITLE_3_1, 
	COLORIZATION_FILE_NAME_1, BANNER_MAIN_IMG_1')
Create colorization filenames where they don't exist
Carry over lifestyles as needed w/ appropriate name
Output an import doc for BCC upload

 """

import sys, threading, ftplib, requests, io, time, json, hashlib, re
from PIL import Image

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
		ftp.storbinary(f"STOR {name}.png", fp = binary) ## TESTING ONLY
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
	except KeyError as err:
		return None

def cleanup_banner_img_name(data):
	# take a banner main image and remove the extra crap
	#/is/image/rhis/cat7760026?wid=696&fmt=jpeg&qlt=90,0&op_sharpen=0&resMode=sharp&op_usm=0.6,1.0,5,0&iccEmbed=1
	#remove everything before the '/'
	# remove everything after the '?'
	data = re.sub('.*\/','',data)
	data = re.sub('\?.*','',data)
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
	originating_name = f"{file_data[0]}"
	# process both RHR and non-RHR
	original_file = download(originating_name)
	if original_file == None: 
		return
	new_name = f"{file_data[1]}"
	output = io.BytesIO()
	original_file.save(output, format = "PNG")
	upload_to_ftp(output, new_name)
			

def main():
	if len(sys.argv) != 2: 
		print(f'Incorrect arguments. Expected 1 got {len(sys.argv)-1}')
		return
	CSV = sys.argv[1]
	with open(CSV, 'r') as csv_file:
		for _ in csv_file.readlines():
			line = _.split(',')
			if line[0] == 'DISPLAY_NAME': continue
			# determine if the swatch is in the shown-in copy for the CG
			# if it's not, continue
			if not line[7].replace('Shown In ',"") in line[5]: continue
			#determine which image to use - it's either the category ID or the cleaned up version of the Banner Main Image
			banner_main_image = cleanup_banner_img_name(line[8])
			donor_image = None
			if banner_main_image != '' and image_exists(banner_main_image):
				donor_image = banner_main_image
			elif image_exists(line[6]):
				donor_image = line[6]
			else:
				# need to handle neither image existing 
				continue
			colorization_filename = hashlib.shake_128(line[0].encode()).hexdigest(4)
			recipient_filename = f'{colorization_filename}_cl{line[4]}'
			transfer_file((donor_image, recipient_filename))
