"""同批采点偏移估计与坐标校正。

对照（Control）是一次复测得到的入口真实坐标。同一采点批次的点位常
整体平移，因此用该批次对照偏移的中位数估偏；中位数对批次里个别错标
不敏感。入口自身若也是对照，估计自身校正时必须排除自己的对照，否则
残差恒为零，等于拿自己的点校正自己。对照太少或离散过大时无法确认
可信偏移，校正不应用，候选沿用文字分。
"""
import math
from statistics import median

from .models import Batch, Control, Entrance
from .common import rows

LAT_M = 111320.0            # 每纬度米数
MIN_CONTROLS = 2            # 少于两个对照无法区分整体偏移与个别错标
CREDIBLE_MEDIAN_M = 10.0    # 对照残差中位数上限
CREDIBLE_MAX_M = 25.0       # 对照残差最大值上限


def offset_m(observed, true):
    """观测坐标相对真实坐标的偏移，返回（东向米，北向米）。"""
    lat = (observed['lat'] + true['lat']) / 2
    east = (observed['lng'] - true['lng']) * LAT_M * math.cos(math.radians(lat))
    north = (observed['lat'] - true['lat']) * LAT_M
    return east, north


def estimate_from_items(items):
    """用一组对照偏移估批次平移。items 每项含 control_id/east/north 米。"""
    n = len(items)
    if n < MIN_CONTROLS:
        return {'credible': False, 'count': n, 'shift_east': None, 'shift_north': None,
                'residual_median': None, 'residual_max': None,
                'control_ids': [x['control_id'] for x in items], 'controls': items,
                'reason': f'同批可用对照仅 {n} 个（至少 {MIN_CONTROLS} 个），无法估偏，沿用文字分'}
    east = median([x['east'] for x in items])
    north = median([x['north'] for x in items])
    residuals = [math.hypot(x['east'] - east, x['north'] - north) for x in items]
    med = median(residuals)
    maximum = max(residuals)
    # 两个对照时中位数退化，必须彼此高度一致才算可信，否则无法与个别错标区分。
    credible = med <= CREDIBLE_MEDIAN_M and maximum <= CREDIBLE_MAX_M and (n >= 3 or maximum <= 5.0)
    reason = '' if credible else (
        f'同批对照离散过大（中位残差 {med:.1f} 米、最大 {maximum:.1f} 米），'
        '无法确认可信偏移，沿用文字分')
    return {'credible': credible, 'count': n, 'shift_east': east, 'shift_north': north,
            'residual_median': med, 'residual_max': maximum,
            'control_ids': [x['control_id'] for x in items], 'controls': items,
            'reason': reason}


def _estimate(controls, by_id, exclude_entrance_id):
    kept = [c for c in controls if c.entrance_id != exclude_entrance_id]
    items = []
    for c in kept:
        e = by_id.get(c.entrance_id)
        if e is None:
            continue
        east, north = offset_m({'lat': e.lat, 'lng': e.lng},
                               {'lat': c.true_lat, 'lng': c.true_lng})
        items.append({'control_id': c.id, 'entrance_id': e.id, 'entrance_code': e.code,
                      'east': east, 'north': north})
    excluded = [c.id for c in controls if c.entrance_id == exclude_entrance_id]
    est = estimate_from_items(items)
    if excluded and not est['credible'] and est['count'] < MIN_CONTROLS:
        est['reason'] = ('对照门牌自身不参与自身校正，排除自身对照后同批可用对照不足 '
                         f'{MIN_CONTROLS} 个，沿用文字分')
    est['excluded_self_control_ids'] = excluded
    return est


def correction_map(s, entrances=None):
    """批量计算每个入口的校正结果，返回 entrance_id -> 校正记录。"""
    everyone = rows(s, Entrance)
    entrances = list(entrances if entrances is not None else everyone)
    controls = rows(s, Control)
    by_id = {e.id: e for e in everyone}
    batches = {b.id: b for b in rows(s, Batch)}
    grouped = {}
    for c in controls:
        grouped.setdefault(c.batch_id, []).append(c)
    out = {}
    for e in entrances:
        reason_missing = '入口未登记采点批次，未应用距离校正'
        if e.batch_id is None:
            out[e.id] = {'entrance_id': e.id, 'entrance_code': e.code, 'batch_id': None,
                         'batch_code': '', 'applied': False, 'reason': reason_missing,
                         'corrected_lat': None, 'corrected_lng': None,
                         'control_ids': [], 'excluded_self_control_id': None,
                         'estimate': {'credible': False, 'count': 0,
                                      'reason': reason_missing}}
            continue
        est = _estimate(grouped.get(e.batch_id, []), by_id, e.id)
        batch = batches.get(e.batch_id)
        est.update({'batch_id': e.batch_id, 'batch_code': batch.code if batch else '',
                    'total_controls': len(grouped.get(e.batch_id, []))})
        excluded = est['excluded_self_control_ids']
        if est['credible']:
            lat = e.lat - est['shift_north'] / LAT_M
            lng = e.lng - est['shift_east'] / (LAT_M * math.cos(math.radians(e.lat)))
            out[e.id] = {'entrance_id': e.id, 'entrance_code': e.code,
                         'batch_id': e.batch_id, 'batch_code': est['batch_code'],
                         'applied': True, 'reason': '', 'corrected_lat': lat,
                         'corrected_lng': lng, 'control_ids': est['control_ids'],
                         'excluded_self_control_id': excluded[0] if excluded else None,
                         'estimate': est}
        else:
            out[e.id] = {'entrance_id': e.id, 'entrance_code': e.code,
                         'batch_id': e.batch_id, 'batch_code': est['batch_code'],
                         'applied': False, 'reason': est['reason'],
                         'corrected_lat': None, 'corrected_lng': None,
                         'control_ids': est['control_ids'],
                         'excluded_self_control_id': excluded[0] if excluded else None,
                         'estimate': est}
    return out


def batch_summaries(s, entrances=None):
    """批次级估偏摘要，供核验页面展示用过哪些对照。"""
    by_id = {e.id: e for e in rows(s, Entrance)}
    controls = rows(s, Control)
    out = []
    for b in rows(s, Batch):
        est = _estimate([c for c in controls if c.batch_id == b.id], by_id, None)
        out.append({'batch_id': b.id, 'batch_code': b.code, 'batch_name': b.name,
                    'credible': est['credible'], 'count': est['count'],
                    'shift_east': est['shift_east'], 'shift_north': est['shift_north'],
                    'residual_median': est['residual_median'],
                    'residual_max': est['residual_max'],
                    'control_ids': est['control_ids'], 'reason': est['reason']})
    return out
