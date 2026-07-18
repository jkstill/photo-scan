

@clear_for_spool

set pagesize 0
set linesize 100 trimspool on
col tag format a40
col tag_count format 999999

spool tag-count.txt

with tag_source as (
select p.photo_id,
       jt.tag
from   photo_ai p,
       json_table(
         p.tags_json,
         '$[*]'
         columns (
           tag varchar2(100) path '$'
         )
       ) jt
)
select t.tag, count(*) tag_count
from tag_source t
group by t.tag
order by 2
/

spool off
--ed tag-count.txt

