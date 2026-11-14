create table if not exists vishnu_workspaces (
  user_id text primary key,
  doc text not null,
  updated_at timestamptz not null default now()
);
