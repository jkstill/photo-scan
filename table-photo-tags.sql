create table photo_tags (
  tag        varchar2(100) not null,
  tag_count  number default 0 not null,
  updated_ts timestamp default systimestamp,
  constraint pk_photo_tags primary key (tag)
);
