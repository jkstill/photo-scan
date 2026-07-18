create table photo_tags (
  tag        text primary key,
  tag_count  integer default 0 not null,
  updated_ts text default current_timestamp
);
