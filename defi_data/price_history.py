"""Price availability and source age, with explicit on-chain ordering."""
from bisect import bisect_left,bisect_right
from decimal import Decimal

PRICE_SCHEMA_VERSION=2
BLOCK_END=2**63-1


def build_price_index(rows):
    feeds={}
    for raw in rows:
        if int(raw.get('schema_version',0))!=PRICE_SCHEMA_VERSION:
            raise ValueError('Legacy price history lacks availability/order metadata; rerun defi_data.recovery_prices')
        row=dict(raw)
        for field in ('stamp','available_stamp','block','transaction_index','log_index'):
            row[field]=int(row[field])
        if row['stamp']<=0 or row['stamp']>row['available_stamp'] or Decimal(row['price_usd'])<=0:
            raise ValueError('Invalid price timestamp or nonpositive quote')
        row['order']=(row['block'],row['transaction_index'],row['log_index'])
        feeds.setdefault(row['feed'],[]).append(row)
    indexes={}
    for feed,samples in feeds.items():
        samples.sort(key=lambda r:r['order'])
        keys=[r['order'] for r in samples]
        if len(set(keys))!=len(keys):raise ValueError('Duplicate price observation order')
        by_time=sorted(samples,key=lambda r:(r['available_stamp'],r['order']))
        indexes[feed]={'rows':samples,'keys':keys,'by_time':by_time,
                       'available_times':[r['available_stamp'] for r in by_time]}
    return indexes


def price_before_event(index,block,transaction_index,log_index,stamp):
    """Only observations strictly before the event in execution order."""
    i=bisect_left(index['keys'],(block,transaction_index,log_index))-1
    if i<0:return None
    row=index['rows'][i]
    return row if row['available_stamp']<=stamp else None


def price_at_time(index,stamp):
    """Latest observation available by this UTC timestamp, including block-end seeds."""
    i=bisect_right(index['available_times'],stamp)-1
    return index['by_time'][i] if i>=0 else None
