import json, tempfile, unittest
from pathlib import Path
from scripts.territory import import_territory, load_territory, contains

# Synthetic unit square; never production geography.
def fixture():
    return {'type':'FeatureCollection','features':[{'type':'Feature','properties':{'zone':'TEST','scope':'CORE_GDL','density':'high'},'geometry':{'type':'Polygon','coordinates':[[[0,0],[0.02,0],[0.02,0.02],[0,0.02],[0,0]],[[0.008,0.008],[0.012,0.008],[0.012,0.012],[0.008,0.012],[0.008,0.008]]]}}]}

class TerritoryTests(unittest.TestCase):
    def test_hole_boundary_scope(self):
        geo=fixture()
        self.assertTrue(contains(geo,.005,.005))
        self.assertFalse(contains(geo,.01,.01))
        self.assertFalse(contains(geo,.03,.01))
        self.assertTrue(contains(geo,0,0))
    def test_approval_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.geojson'; dest=Path(tmp)/'territory.geojson'
            source.write_text(json.dumps(fixture()))
            import_territory(source,dest)
            with self.assertRaises(ValueError): load_territory(dest)
            import_territory(source,dest,approved=True)
            self.assertEqual(len(load_territory(dest)['features']),1)
    def test_invalid_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'bad.geojson'; geo=fixture()
            geo['features'][0]['geometry']['coordinates'][0][0]=[999,0]
            source.write_text(json.dumps(geo))
            with self.assertRaises(ValueError): import_territory(source,Path(tmp)/'out.json')
    def test_kml(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'map.kml'
            source.write_text('<kml><Document><Placemark><name>TEST</name><Polygon><outerBoundaryIs><LinearRing><coordinates>0,0 0.02,0 0.02,0.02 0,0.02 0,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>')
            geo=import_territory(source,Path(tmp)/'out.json',scope='CORE_GDL',approved=True)
            self.assertTrue(contains(geo,.01,.01))
    def test_multi_kmz_merge(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.geojson'; dest=Path(tmp)/'territory.geojson'
            source.write_text(json.dumps(fixture()))
            import_territory(source,dest,approved=True)
            geo=fixture(); geo['features'][0]['geometry']={'type':'MultiPolygon','coordinates':[geo['features'][0]['geometry']['coordinates']]}
            source.write_text(json.dumps(geo))
            result=import_territory(source,dest,scope='AMG_FULL',approved=True)
            self.assertEqual(len(result['features']),2)
            self.assertTrue(contains(result,.005,.005))
            archive=Path(tmp)/'map.kmz'
            with zipfile.ZipFile(archive,'w') as handle:
                handle.writestr('doc.kml','<kml><Placemark><name>KMZ_TEST</name><Polygon><outerBoundaryIs><LinearRing><coordinates>0,0 0.02,0 0.02,0.02 0,0.02 0,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></kml>')
            self.assertEqual(len(import_territory(archive,dest,scope='CORE_GDL')['features']),3)
    def test_reject_unsafe_xml_and_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.kml'
            path.write_text('<!DOCTYPE x [<!ENTITY a "b">]><kml/>')
            with self.assertRaises(ValueError): import_territory(path,Path(tmp)/'out.json')
            path=Path(tmp)/'empty.geojson'; path.write_text('{"type":"FeatureCollection","features":[]}')
            with self.assertRaises(ValueError): import_territory(path,Path(tmp)/'out.json')
            with self.assertRaises(ValueError): load_territory(path)
    def test_scope_required_and_geometry_rejections(self):
        from scripts.territory import _validate_geometry
        for geometry in ({'type':'Point','coordinates':[0,0]}, {'type':'Polygon','coordinates':[]}, {'type':'Polygon','coordinates':[[]]}, {'type':'Polygon','coordinates':[[[0,0],[1,1],[2,2],[0,0]]]}):
            with self.assertRaises(ValueError): _validate_geometry(geometry)
        with self.assertRaises(ValueError): contains(fixture(),0,0,'unknown')

    def test_amg_scope_does_not_treat_other_layers_as_amg(self):
        layered = fixture()
        layered['features'].append({
            'type': 'Feature',
            'properties': {'zone': 'URBAN', 'scope': 'URBAN_AMG', 'density': 'high', 'approved': True},
            'geometry': {'type': 'Polygon', 'coordinates': [[[2,2],[3,2],[3,3],[2,3],[2,2]]]},
        })
        self.assertFalse(contains(layered, 2.5, 2.5, 'AMG_FULL'))
        self.assertTrue(contains(layered, 2.5, 2.5, 'URBAN_AMG'))
