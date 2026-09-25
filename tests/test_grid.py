import unittest
from tests.test_territory import fixture
from scripts.grid import generate_grid, refine_grid
from scripts.territory import contains
class GridTests(unittest.TestCase):
    def test_grid_clipped_and_repeatable(self):
        points=generate_grid(fixture(),{},scope='CORE_GDL')
        self.assertTrue(points)
        self.assertEqual(points,generate_grid(fixture(),{},scope='CORE_GDL'))
        self.assertTrue(all(contains(fixture(),p['latitude'],p['longitude']) for p in points))
        self.assertEqual(len({p['point_id'] for p in points}),len(points))
    def test_refinement(self):
        points=generate_grid(fixture(),{},scope='CORE_GDL')
        refined=refine_grid(points,{p['point_id']:100 for p in points},fixture(),{})
        self.assertTrue(refined)
        self.assertTrue(all(p['pass']==2 for p in refined))

    def test_scope_limit_and_outputs(self):
        import tempfile, json
        from pathlib import Path
        from scripts.grid import write_grid
        with self.assertRaises(ValueError): generate_grid(fixture(),{})
        with self.assertRaises(ValueError): generate_grid(fixture(),{'max_grid_points':1},scope='CORE_GDL')
        with self.assertRaises(ValueError): generate_grid(fixture(),{'densities':{'high':{'cell_km':0}}},scope='CORE_GDL')
        points=generate_grid(fixture(),{},scope='CORE_GDL',pass_number=2)
        with tempfile.TemporaryDirectory() as tmp:
            csv=Path(tmp)/'grid.csv'; preview=Path(tmp)/'preview.geojson'
            write_grid(points,csv,preview)
            self.assertEqual(len(json.loads(preview.read_text())['features']),len(points))
            self.assertIn('point_id',csv.read_text(encoding='utf-8-sig'))
        self.assertEqual(refine_grid(points,{},fixture(),{}),[])

    def test_historical_yield_selects_profile_independent_of_municipality(self):
        geo=fixture()
        left=geo['features'][0]
        left['properties']={**left['properties'],'zone':'WEST','municipality':'TEST_MUNICIPALITY','density':'medium'}
        left['geometry']={'type':'Polygon','coordinates':[[[0,0],[0.02,0],[0.02,0.02],[0,0.02],[0,0]]]}
        right={
            'type':'Feature',
            'properties':{'zone':'EAST','scope':'CORE_GDL','municipality':'TEST_MUNICIPALITY','density':'medium'},
            'geometry':{'type':'Polygon','coordinates':[[[0.03,0],[0.05,0],[0.05,0.02],[0.03,0.02],[0.03,0]]]},
        }
        geo['features'].append(right)
        coverage={
            'adaptive_grid':{'enabled':True,'min_observations':2,'high_yield':80,'medium_yield':30},
            'historical_yields':{
                'WEST':{'results':200,'observations':2},
                'EAST':{'results':20,'observations':2},
            },
        }
        points=generate_grid(geo,coverage,scope='CORE_GDL')
        by_zone={zone:[p for p in points if p['zone']==zone] for zone in ('WEST','EAST')}
        self.assertTrue(by_zone['WEST'] and by_zone['EAST'])
        self.assertTrue(all(p['cell_km']==0.5 and p['depth']==8 for p in by_zone['WEST']))
        self.assertTrue(all(p['cell_km']==1.5 and p['depth']==5 for p in by_zone['EAST']))

    def test_adaptive_grid_falls_back_when_history_is_insufficient(self):
        coverage={
            'adaptive_grid':{'enabled':True,'min_observations':3,'high_yield':80,'medium_yield':30},
            'historical_yields':{'TEST':{'results':500,'observations':1}},
            'densities':{'high':{'cell_km':0.6}},
        }
        points=generate_grid(fixture(),coverage,scope='CORE_GDL')
        self.assertTrue(points)
        self.assertTrue(all(p['cell_km']==0.6 for p in points))

    def test_adaptive_grid_rejects_invalid_history(self):
        coverage={
            'adaptive_grid':{'enabled':True},
            'historical_yields':{'TEST':{'results':-1,'observations':2}},
        }
        with self.assertRaises(ValueError):
            generate_grid(fixture(),coverage,scope='CORE_GDL')

    def test_grid_never_mixes_overlapping_scopes(self):
        geo = fixture()
        amg = {**geo['features'][0], 'properties': {**geo['features'][0]['properties'],
               'zone': 'AMG', 'scope': 'AMG_FULL', 'density': 'medium'}}
        geo['features'].append(amg)
        core = generate_grid(geo, {}, scope='CORE_GDL')
        amg_points = generate_grid(geo, {}, scope='AMG_FULL')
        self.assertTrue(core and amg_points)
        self.assertEqual({'CORE_GDL'}, {p['scope'] for p in core})
        self.assertEqual({'AMG_FULL'}, {p['scope'] for p in amg_points})
