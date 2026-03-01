

create table photo_ai (
  photo_id     number generated always as identity primary key,
  file_path    varchar2(1024) not null,
  file_sha256  varchar2(64)   not null,
  caption      clob,
  tags_json    json,
  embed_model  varchar2(64) default 'mxbai-embed-large',
  embedding    vector(1024, float32),
  created_ts   timestamp default systimestamp,
  constraint uq_photo_ai unique (file_sha256)
);


