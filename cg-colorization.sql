drop table cg_color_child_cats;
drop table cg_color_grand_children;
drop table cg_color_prod_lists;
drop table cg_parent_child_prods;
drop table parent_prod_agg;
drop table cg_color_matches;

-- select the child categories
create table cg_color_child_cats as
select 
DCS_CAT_CHLDCAT.CHILD_CAT_ID, dcs_category.display_name,
rh_category.COLORIZER, rh_category.COLORIZE_TYPE
from
DCS_CAT_CHLDCAT
join dcs_category on dcs_category.category_id = DCS_CAT_CHLDCAT.CHILD_CAT_ID
join rh_category on rh_category.category_id = DCS_CAT_CHLDCAT.CHILD_CAT_ID
where 
DCS_CAT_CHLDCAT.category_id in ('cat10180128') -- the parent category for all the CGs you want to update (not grandparent)
and dcs_category.END_DATE is null
and rh_category.REMOVE_FROM_CATALOG_BROWSE = 0
order by dcs_category.display_name;



-- get child anc categories
create table cg_color_grand_children as 
select distinct
cg_color_child_cats.CHILD_CAT_ID parent_category,
NVL(dcs_cat_anc_cats.category_id, cg_color_child_cats.CHILD_CAT_ID) child_category,
NVL(dcs_category.display_name, cg_color_child_cats.display_name) child_display
from cg_color_child_cats
left join dcs_cat_anc_cats on dcs_cat_anc_cats.anc_category_id = cg_color_child_cats.CHILD_CAT_ID
left join dcs_category on dcs_category.category_id = dcs_cat_anc_cats.category_id
order by cg_color_child_cats.CHILD_CAT_ID;



-- get prods for each child_category_id
create table cg_color_prod_lists as 
select 
child_category, 
dcs_product.product_id
from 
cg_color_grand_children
join dcs_cat_chldprd on dcs_cat_chldprd.category_id  = cg_color_grand_children.child_category
join dcs_product on dcs_product.product_id = dcs_cat_chldprd.child_prd_id
join rh_product on rh_product.product_id = dcs_cat_chldprd.child_prd_id
where
dcs_product.end_date is null
and rh_product.remove_from_browse = 0;


-- join child_prods to the parent categories
create table cg_parent_child_prods as
select distinct
cg_color_grand_children.parent_category,
cg_color_prod_lists.product_id,
row_number() over (partition by cg_color_grand_children.parent_category order by cg_color_prod_lists.product_id) rn
from
cg_color_grand_children
join cg_color_prod_lists on cg_color_prod_lists.child_category = cg_color_grand_children.child_category
order by cg_color_grand_children.parent_category;



create table parent_prod_agg as 
select
parent_category,
listagg(product_id) within group(order by product_id) product_list
from
cg_parent_child_prods
where rn<200
group by parent_category;

-- get the matches

create table cg_color_matches as
select ppa1.parent_category category1, ppa2.parent_category category2
from parent_prod_agg ppa1
join parent_prod_agg ppa2 on ppa2.product_list = ppa1.product_list
join dcs_category dcat1 on dcat1.category_id = ppa1.parent_category
join dcs_category dcat2 on dcat2.category_id = ppa1.parent_category
where not ppa1.parent_category = ppa2.parent_category
order by ppa1.parent_category;


 
-- run below for export data
select distinct 
dcs_category.display_name, rcat1.SUBTITLE_3, rcat1.COLORIZATION_FILE_NAME, rcat1.BANNER_MAIN_IMG,
rh_product.sale_swatch, rh_swatch.display_name, 
cg_color_matches.category2, rcat2.SUBTITLE_3, rcat2.COLORIZATION_FILE_NAME, rcat2.BANNER_MAIN_IMG
from
rh_product
join cg_parent_child_prods on cg_parent_child_prods.product_id = rh_product.product_id
join rh_swatch on rh_swatch.swatch_id = rh_product.sale_swatch
join cg_color_matches on cg_color_matches.category1 = cg_parent_child_prods.parent_category
join cg_color_matches on cg_color_matches.category2 = cg_parent_child_prods.parent_category
join rh_category rcat1 on rcat1.category_id = cg_color_matches.category1
join rh_category rcat2 on rcat2.category_id = cg_color_matches.category2
join dcs_category on dcs_category.category_id = rcat1.category_id
where rh_product.product_id in cg_parent_child_prods.product_id
order by dcs_category.display_name;