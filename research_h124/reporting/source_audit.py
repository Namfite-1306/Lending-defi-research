"""Independent read-only checks of new source pages, quotes and primary model scope."""
import gzip,json,sqlite3
from pathlib import Path
from . import PACKAGE_DIR,source_files
from .next_common import *
from .market_prices import parse_page,LATENCY

def run():
    errors=[];checked=0;trades_checked=0;quarantined=[]
    c=sqlite3.connect(f'file:{(DATA_NEXT/"kraken.sqlite").as_posix()}?mode=ro',uri=True)
    for since,start,end,cursor,n,sha in c.execute('SELECT since,start,end,cursor,rows,sha256 FROM pages'):
        path=DATA_NEXT/'trade_pages'/(since+'.json.gz')
        try:
            if digest(path)!=sha:raise ValueError('Page SHA256 mismatch')
            with gzip.open(path,'rt',encoding='utf8') as f:payload=json.load(f)
            reason=c.execute('SELECT reason FROM quarantined_pages WHERE since=?',(since,)).fetchone()
            rows,a,b,last=parse_page(payload,since,allow_reviewed_gap=bool(reason))
            if reason:quarantined.append({'since':since,'reason':reason[0],'excluded_from_coverage':True})
            if (a,b,last,len(rows))!=(start,end,cursor,n):raise ValueError('Page ledger mismatch')
            for row in rows:
                actual=c.execute('SELECT id,stamp,price,volume FROM trades WHERE id=?',(row[0],)).fetchone()
                if actual!=row:raise ValueError('Parsed trade differs from database')
            checked+=1;trades_checked+=len(rows)
        except Exception as exc:errors.append({'since':since,'error':str(exc)[:180]})
    quotes=read(OUT/'market_event_quotes.csv');quote_checks=0
    for r in quotes:
        if r['market_debt_usd']=='':continue
        trade=c.execute('SELECT stamp,price,id FROM trades WHERE id=?',(int(r['market_trade_id']),)).fetchone()
        if not trade or not trade[0]<int(r['stamp'])-LATENCY or abs(float(r['market_price_usd'])-float(trade[1]))>1e-12 or not 0<float(r['market_age_seconds'])<=3600:
            errors.append({'episode':r['episode'],'error':'Quote availability/value mismatch'})
        else:quote_checks+=1
    c.close()
    models=read(OUT/'h3/model_comparison.csv');comparison=read(OUT/'h3/common_primary_comparison.csv')
    support={(int(r['test_bins']),int(r['test_events'])) for r in models+comparison}
    if support!={(78643,10448)}:errors.append({'error':'Models have differing primary test support','support':list(support)})
    scope=load(OUT/'h1_primary_scope.json',{})
    if scope.get('full_snapshots')!=13 or scope.get('required_snapshots')!=13:errors.append({'error':'H1 revised scope incomplete'})
    inputs=[DATA_NEXT/'activity_panel.npz',V2_OUT/'h4_prefix_data_readiness.json',V1_OUT/'h2/episodes.csv',V1_OUT/'h2/collateral_legs.csv']
    old_root=CANONICAL/'results/full_7rq_20261022_final'
    protected={str(old_root/name):value for name,value in load(old_root/'result_checksums.json',{}).items()}
    for baseline in [V2_OUT/'old_output_hashes.json',REPAIR_OUT/'protected_outputs.json']:
        protected.update(load(baseline,{}))
    mismatches=[name for name,value in protected.items() if not Path(name).is_file() or digest(name)!=value]
    if not protected or mismatches:errors.append({'error':'Frozen earlier output mismatch or missing baseline','files':mismatches})
    result={'updated_utc':now(),'passed':not errors,'errors':errors,'pages_verified':checked,'page_trade_rows_verified_including_overlap':trades_checked,
      'old_files_checked':len(protected),'old_outputs_preserved':bool(protected) and not mismatches,'old_output_mismatches':mismatches,
      'priced_quotes_verified':quote_checks,'quarantined_pages':quarantined,'same_test_support':sorted(support),'primary_end_exclusive':PRIMARY_END_UTC,
      'input_hashes':{str(p.relative_to(CANONICAL)):digest(p) for p in inputs},
      'source_hashes':{p.relative_to(PACKAGE_DIR).as_posix():digest(p) for p in source_files()},
      'limitations':['Verifies stored source consistency; not an independent exchange/provider confirmation','PIT model misspecification remains despite technical audit passing']}
    save(OUT/'source_audit.json',result)
    if errors:raise RuntimeError('Source audit failed; inspect source_audit.json')
    print('SOURCE AUDIT',checked,'pages;',quote_checks,'priced quotes; same test',support,flush=True)
    return result

if __name__=='__main__':run()
