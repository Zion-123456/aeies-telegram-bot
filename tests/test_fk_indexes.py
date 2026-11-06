def test_every_foreign_key_has_full_valid_prefix_index(world):
    with world.db.transaction() as c:
        missing = c.execute(
            "SELECT conname FROM pg_constraint f WHERE contype='f' AND connamespace='aeies'::regnamespace AND NOT EXISTS(SELECT 1 FROM pg_index i WHERE i.indrelid=f.conrelid AND i.indisvalid AND i.indpred IS NULL AND (i.indkey::smallint[])[0:cardinality(f.conkey)-1] @> f.conkey)"
        ).fetchall()
        assert missing == []
