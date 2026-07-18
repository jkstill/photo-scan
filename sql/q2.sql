select jt.tag
from photo_ai p ,
json_table(
         p.tags_json,
         '$[*]'
         columns (
           tag varchar2(100) path '$'
         )
       ) jt
where photo_id = 2017
/
