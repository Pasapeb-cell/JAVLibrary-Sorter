-- Reduced real-schema fixture from the public R18.dev PostgreSQL dump.
COPY public.derived_video (content_id, dvd_id, dvd_id_norm) FROM stdin;
118abc00001	ABC-1	ABC1
118abc00002	ABC-2	ABC2
118abc00003	ABC-3	ABC3
\.
COPY public.derived_actress (id, name_romaji, name_kanji, name_kana) FROM stdin;
a1	Alice Example	\N	\N
a2	Bob Example	ボブ	ぼぶ
a3	Carol Example	\N	\N
\.
COPY public.derived_video_actress (content_id, actress_id, ordinality) FROM stdin;
118abc00001	a1	1
118abc00001	a2	2
118abc00002	a3	1
118abc00003	a1	1
118abc00003	a3	2
\.
