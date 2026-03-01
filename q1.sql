select file_path, caption
from photo_ai
where json_exists(tags_json, '$?(@ == "car")')
/
