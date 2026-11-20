-- 班级退场清理任务：ORM 启动时自动建表，本文件保留实际 DDL 记录。
CREATE TABLE public.cleanups (
    id integer NOT NULL,
    class_code character varying(50) NOT NULL,
    state character varying(20),
    note text,
    facts_total integer,
    facts_removed integer,
    snapshots_total integer,
    snapshots_done integer,
    records_removed integer,
    remaining json,
    error text,
    created_by character varying(100),
    created character varying(40),
    finished character varying(40)
);

CREATE SEQUENCE public.cleanups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.cleanups_id_seq OWNED BY public.cleanups.id;

ALTER TABLE ONLY public.cleanups ALTER COLUMN id SET DEFAULT nextval('public.cleanups_id_seq'::regclass);

ALTER TABLE ONLY public.cleanups
    ADD CONSTRAINT cleanups_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.cleanups
    ADD CONSTRAINT cleanups_class_code_key UNIQUE (class_code);
