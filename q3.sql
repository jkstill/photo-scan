select --jt.tag
file_path,caption
from photo_ai p ,
json_table(
         p.tags_json,
         '$[*]'
         columns (
           tag varchar2(100) path '$'
         )
       ) jt
where jt.tag = 'painting'
/
