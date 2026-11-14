create table if not exists vishnu_recovery (
  user_id text primary key,
  email text not null,
  code_hashes text not null,
  updated_at timestamptz not null default now()
);

create table if not exists vishnu_passkeys (
  credential_id text primary key,
  user_id text not null,
  public_key text not null,
  counter bigint not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists vishnu_passkeys_user_idx on vishnu_passkeys (user_id);

create table if not exists vishnu_challenges (
  id text primary key,
  user_id text,
  challenge text not null,
  kind text not null,
  expires_at timestamptz not null
);
