import csv
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.normalize import normalize_name, normalize_record, read_raw
from scripts.dedupe import deduplicate
from scripts.brands import group_brands
from scripts.exports import write_csv, export_mymaps, compare_records
from scripts.storage import init_db, save_run
from scripts.pipeline import process_snapshot


class ProcessingTests(unittest.TestCase):
    def place(self, **kw):
        return normalize_record({'title': 'Café Azul', 'latitude': 20.7,
                                 'longitude': -103.4, **kw})

    def test_normalize_preserves_unknown_and_invalid_coordinates(self):
        self.assertEqual(normalize_name(' Café   AZÚL! '), 'cafe azul')
        p = self.place(latitude='NaN', future_field={'nested': 3})
        self.assertIsNone(p['latitude'])
        self.assertEqual(p['future_field'], {'nested': 3})

    def test_dedupe_never_collapses_branches_by_shared_phone(self):
        rows = [self.place(place_id='a', phone='3312345678'),
                self.place(place_id='b', phone='3312345678'),
                self.place(place_id='a', category='Cafe')]
        result = deduplicate(rows)
        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0]['provenance']), 2)

    def test_fallback_name_address_and_not_coordinates_only(self):
        self.assertEqual(len(deduplicate([self.place(address='Uno 1'), self.place(address='Uno 1')])), 1)
        self.assertEqual(len(deduplicate([self.place(title='Uno'), self.place(title='Dos')])), 2)

    def test_brand_domain_evidence_and_aggregator_exclusion(self):
        rows = [self.place(place_id='a', website='https://azul.mx/a'),
                self.place(place_id='b', website='https://azul.mx/b')]
        places, brands, ambiguous = group_brands(deduplicate(rows))
        self.assertEqual(brands[0]['branches_amg'], 2)
        self.assertEqual(brands[0]['brand_scope'], 'uncertain')
        rows = [self.place(place_id='a', title='Uno', website='https://facebook.com/uno'),
                self.place(place_id='b', title='Dos', website='https://facebook.com/dos')]
        self.assertEqual(len(group_brands(deduplicate(rows))[1]), 2)

    def test_exact_non_generic_name_can_form_watchlist_without_domain(self):
        rows = [self.place(place_id='a', address='Uno 1'),
                self.place(place_id='b', address='Dos 2')]
        _, brands, _ = group_brands(deduplicate(rows))
        self.assertEqual(1, len(brands))
        self.assertEqual(2, brands[0]['branches_amg'])
        generic = [self.place(place_id='c', title='Cafetería', address='Tres 3'),
                   self.place(place_id='d', title='Cafetería', address='Cuatro 4')]
        self.assertEqual(2, len(group_brands(deduplicate(generic))[1]))
        mixed = [self.place(place_id='e', website='https://cafeazul.mx', address='Cinco 5'),
                 self.place(place_id='f', address='Seis 6')]
        self.assertEqual(1, len(group_brands(deduplicate(mixed))[1]))
        common = [self.place(place_id='g', title='La Casa', address='Siete 7'),
                  self.place(place_id='h', title='La Casa', address='Ocho 8')]
        self.assertEqual(2, len(group_brands(deduplicate(common))[1]))

    def test_comparison_missing_is_not_closed_and_reappears(self):
        old = [self.place(place_id='a'), self.place(place_id='b')]
        new = [self.place(place_id='a', review_count=3), self.place(place_id='c')]
        changes = compare_records(old, new, {'place_id:c'})
        self.assertEqual({r['change'] for r in changes}, {'changed', 'missing_this_run', 'reappeared'})

    def test_csv_safety_chunking_and_raw_formats(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write_csv(root/'safe.csv', [{'title': '=CMD()', 'latitude': -12.3}])
            with (root/'safe.csv').open(encoding='utf-8-sig') as f:
                row = next(csv.DictReader(f))
            self.assertEqual(row['title'], "'=CMD()")
            self.assertEqual(row['latitude'], '-12.3')
            files = export_mymaps(root/'mymaps', [self.place() for _ in range(2001)])
            self.assertEqual(len(files), 2)
            (root/'raw.jsonl').write_text('{"title":"a"}\n{"title":"b"}\n')
            self.assertEqual(len(list(read_raw(root/'raw.jsonl'))), 2)

    def test_database_idempotent_observations(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d)/'db.sqlite'
            init_db(db)
            rows, brands, _ = group_brands(deduplicate([self.place(place_id='a')]))
            for _ in range(2):
                save_run(db, {'run_id':'r', 'month':'2026-01', 'scope':'AMG_FULL'}, rows, brands)
            with sqlite3.connect(db) as con:
                self.assertEqual(con.execute('select count(*) from observations').fetchone()[0], 1)
            con.close()

    def test_pipeline_clips_preserves_provenance_and_isolates_pilot(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'config').mkdir()
            (root/'config/categories.json').write_text('{"merchant_families":{"Cafe":["cafe"]}}')
            snapshot = root/'tests/pilot'
            snapshot.mkdir(parents=True)
            raw = snapshot/'raw.jsonl'
            records = [{'place_id':'a','title':'Cafe','category':'Cafe','latitude':20.7,'longitude':-103.4,'input_id':'j'},
                       {'place_id':'b','title':'Outside','latitude':0,'longitude':0}]
            raw.write_text('\n'.join(json.dumps(r) for r in records))
            territory = {'features':[{'properties':{'scope':'CORE_GDL','zone':'core'},'geometry':{
                'type':'Polygon','coordinates':[[[-104,20],[-103,20],[-103,21],[-104,21],[-104,20]]]}}]}
            manifest = {'run_id':'pilot','scope':'AMG_FULL','status':'completed','batches':[
                {'batch_id':'one','status':'completed','raw_file':str(raw),'jobs':[{'job_id':'j','query':'cafe','zone':'core'}]}]}
            report = process_snapshot(root,snapshot,territory,manifest)
            self.assertEqual(report['unique_places'],1)
            self.assertEqual(report['excluded_records'],1)
            self.assertFalse((root/'data/foodscan.db').exists())
            self.assertTrue((snapshot/'processed/foodscan.db').exists())
            place = json.loads((snapshot/'processed/places.json').read_text())[0]
            self.assertEqual(place['provenance'][0]['job_id'],'j')
            self.assertEqual(place['merchant_family'],'Cafe')
            self.assertFalse(report['incomplete'])


if __name__ == '__main__':
    unittest.main()
