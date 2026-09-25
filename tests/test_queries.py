import tempfile, unittest
from pathlib import Path
from scripts.queries import make_jobs, write_batches
class QueryTests(unittest.TestCase):
    def test_jobs_and_depth_batches(self):
        points=[dict(point_id=str(i),latitude=20,longitude=-103,zoom=16,depth=depth,zone='TEST',scope='CORE_GDL',query_profile='FOOD_CORE',**{'pass':1}) for i,depth in enumerate([6,8])]
        jobs=make_jobs(points,{'profiles':{'FOOD_CORE':['tacos','cafetería']}})
        self.assertTrue(jobs)
        self.assertIn('https://www.google.com/maps/search/',jobs[0]['url'])
        with tempfile.TemporaryDirectory() as tmp:
            batches=write_batches(jobs,Path(tmp),50)
            self.assertEqual(len(batches),2)
            self.assertIn(' #!# ',Path(batches[0]['input']).read_text())
    def test_no_newline_query(self):
        with self.assertRaises(ValueError):
            make_jobs([dict(point_id='a',latitude=20,longitude=-103,zoom=16,depth=6,zone='TEST',scope='CORE_GDL',query_profile='FOOD_CORE',**{'pass':1})],{'profiles':{'FOOD_CORE':['bad\nquery']}})
    def test_pilot_strata_and_profiles(self):
        from scripts.queries import pilot_points
        points=[dict(point_id=str(i),latitude=20,longitude=-103,zoom=16,depth=5+i%3,zone=f'Z{i%3}',scope='CORE_GDL',query_profile='FOOD_CORE',**{'pass':1}) for i in range(90)]
        sample=pilot_points(points)
        self.assertEqual(len(sample),15)
        self.assertEqual(len({p['zone'] for p in sample}),3)
        categories={'profiles':{'FOOD_CORE':{'queries':['tacos']},'FOOD_DESSERT':['café']}}
        self.assertEqual(len(make_jobs(points,categories,pilot=True)),30)
        self.assertEqual(len(make_jobs(points,{**categories,'active_queries':['pizza']})),90)
        with self.assertRaises(ValueError): write_batches([],Path('.'),0)
        with self.assertRaises(ValueError): make_jobs([points[0],points[0]],categories)
