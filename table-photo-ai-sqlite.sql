create table photo_ai (
  photo_id            integer primary key autoincrement,
  file_path           text not null,
  file_sha256         text not null,
  caption             text,
  tags_json           text,
  embed_model         text default 'mxbai-embed-large',
  embedding           blob,
  created_ts          text default current_timestamp,
  exif_json           text,
  exif_date_original  text,
  notes               text,
  unique (file_sha256)
);

create index photo_ai_exif_date_idx on photo_ai(exif_date_original);
