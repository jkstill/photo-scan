

create table photo_ai (
  photo_id     number generated always as identity primary key,
  file_path    varchar2(1024) not null,
  file_sha256  varchar2(64)   not null,
  caption      clob,
  tags_json    json,
  embed_model  varchar2(64) default 'mxbai-embed-large',
  embedding    vector(1024, float32),
  created_ts   timestamp default systimestamp,
  exif_json    json,
  exif_date_original timestamp generated always as (
      to_timestamp(
          nullif(
              json_value(exif_json, '$[*]?(@.tag == "DateTimeOriginal").val' returning varchar2(20)),
              '0000:00:00 00:00:00'
          ), 
          'YYYY:MM:DD HH24:MI:SS'
      )
  ) virtual,
  constraint uq_photo_ai unique (file_sha256)
);

create index photo_ai_exif_date_idx on photo_ai(exif_date_original);


