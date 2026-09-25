"""Evidence-based grouping; scope stays uncertain until researched."""
import hashlib
from collections import Counter
from urllib.parse import urlparse
from .normalize import normalize_name

AGGREGATORS = {'facebook.com', 'instagram.com', 'google.com', 'maps.google.com', 'ubereats.com',
               'rappi.com', 'rappi.com.mx', 'whatsapp.com', 'wa.me', 'linktr.ee', 'tripadvisor.com'}
GENERIC_NAMES = {'cafe', 'cafeteria', 'panaderia', 'pasteleria', 'sushi', 'restaurant',
                 'restaurante', 'comida', 'comida para llevar', 'supermercado', 'tienda', 'abarrotes',
                 'la casa', 'el sazon', 'los compadres', 'cocina economica', 'el rincon',
                 'la esquina', 'el patio'}


def domain(value):
    if not isinstance(value, str):
        return ''
    host = (urlparse(value if '://' in value else 'https://' + value).hostname or '').lower().removeprefix('www.')
    return '' if any(host == d or host.endswith('.' + d) for d in AGGREGATORS) else host


def group_brands(rows):
    groups, ambiguous = {}, []
    by_name = {}
    for row in rows:
        name = row.get('normalized_name') or normalize_name(row.get('title'))
        by_name.setdefault(name, []).append(row)
    for name, members in by_name.items():
        hosts = {domain(row.get('website', '')) for row in members} - {''}
        categories = {normalize_name(row.get('google_category') or row.get('category'))
                      for row in members} - {''}
        # Exact name plus one non-conflicting private domain, or exact name plus
        # one shared observed category, is a reasonable chain candidate. A
        # generic/common name or conflicting domains stays split and ambiguous.
        coherent = (name and name not in GENERIC_NAMES and len(hosts) <= 1
                    and bool(hosts or len(categories) == 1 or len(members) >= 2))
        if coherent:
            groups[('entity_name', next(iter(hosts), ''), name)] = members
        else:
            for row in members:
                host = domain(row.get('website', ''))
                key = ('domain_name', host, name) if host and name else ('individual', row['record_id'])
                groups.setdefault(key, []).append(row)
    places, brands = [], []
    names = {}
    for key, members in groups.items():
        brand_id = hashlib.sha256(repr(key).encode()).hexdigest()[:20]
        municipalities = sorted({r.get('municipality') for r in members
                                 if r.get('municipality') not in (None, '', 'UNKNOWN')})
        families = Counter(r.get('merchant_family') for r in members if r.get('merchant_family'))
        ratings = [float(r['review_rating']) for r in members if str(r.get('review_rating', '')).replace('.', '', 1).isdigit()]
        reviews = [int(float(r['review_count'])) for r in members if str(r.get('review_count', '')).replace('.', '', 1).isdigit()]
        websites = sorted({r.get('website') for r in members if r.get('website')})
        phones = sorted({r.get('phone') for r in members if r.get('phone')})
        brand = {'brand_id': brand_id, 'brand_name': members[0].get('title', ''),
                 'branches_amg': len(members), 'branch_count_amg': len(members),
                 'branches_core': sum(bool(r.get('inside_core_periferico', r.get('in_core'))) for r in members),
                 'branch_count_core': sum(bool(r.get('inside_core_periferico', r.get('in_core'))) for r in members),
                 'branch_count_urban_amg': sum(bool(r.get('inside_urban_amg')) for r in members),
                 'municipalities': '; '.join(municipalities),
                 'merchant_family': families.most_common(1)[0][0] if families else '',
                 'rating_avg': round(sum(ratings) / len(ratings), 2) if ratings else '',
                 'reviews_total': sum(reviews), 'website': websites[0] if websites else '',
                 'phones': '; '.join(phones),
                 'brand_scope': 'uncertain', 'confidence': 0.9 if len(members) > 1 else 0.5,
                 'evidence': ('same_name_private_domain' if len(members) > 1 and key[1]
                              else 'exact_normalized_name_distinct_places' if len(members) > 1
                              else 'single_establishment')}
        brands.append(brand)
        for row in members:
            places.append({**row, **brand, 'branch_id': row['record_id'],
                           'branch_name': row.get('title', '')})
        name = members[0].get('normalized_name')
        if name and name in names:
            ambiguous.append({'name': name, 'brand_id_a': names[name], 'brand_id_b': brand_id,
                              'reason': 'Same name without sufficient independent evidence'})
        names[name] = brand_id
    return places, brands, ambiguous[:500]
