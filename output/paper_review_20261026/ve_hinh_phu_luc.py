"""Export appendix A1, C1 and D1 without fitting models or changing source data.

Run from the repository root:
    python output/paper_review_20261026/ve_hinh_phu_luc.py
Requires matplotlib. Outputs PNG (300 dpi), SVG, figure source CSVs and hashes.
"""
import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'deliverables/writing_materials_20261024/evidence'
EXPOSURES = ROOT / 'data/runs/recovery_20261020/processed/exposures_valued_sample.csv'
TOKENS = ROOT / 'data/runs/recovery_20261020/processed/token_registry.csv'


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def write(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(fig, out, name):
    fig.savefig(out / (name + '.png'), dpi=300, bbox_inches='tight', facecolor='white')
    fig.savefig(out / (name + '.svg'), bbox_inches='tight', facecolor='white')
    plt.close(fig)


def build(out):
    out.mkdir(parents=True, exist_ok=True)
    paths = [EVIDENCE/'H1_stress_curves.csv', EVIDENCE/'RQ6_stylized_scenarios.csv', EXPOSURES, TOKENS]
    original = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':10, 'axes.spines.top':False,
                         'axes.spines.right':False, 'svg.fonttype':'none'})

    # A1: exactly the paper's joint/factor-family/1 percentage point grid.
    rows = [r for r in read(paths[0]) if r['scenario']=='joint' and r['mapping']=='factor_family_1to1']
    quarters = sorted({r['quarter'] for r in rows})
    assert len(quarters)==13
    fig, ax = plt.subplots(figsize=(9.5,6.8))
    colors = plt.get_cmap('tab20')
    for n,q in enumerate(quarters):
        group=sorted((r for r in rows if r['quarter']==q),key=lambda r:float(r['shock']))
        assert len(group)==61 and [round(float(r['shock'])*100) for r in group]==list(range(61))
        ax.plot([float(r['shock'])*100 for r in group], [float(r['eligible_debt_share'])*100 for r in group],
                label=q, color=colors(n), linewidth=1.8, linestyle=['-','--','-.',':'][n//4])
    ax.set(xlabel='Joint ETH/BTC price decline (%)', ylabel='Eligible debt / total post-shock debt (%)', xlim=(0,60), ylim=(0,None))
    ax.yaxis.set_major_formatter(PercentFormatter(100))
    ax.grid(alpha=.2)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, ncol=5, loc='lower center', bbox_to_anchor=(.5,.075), frameon=False, fontsize=9)
    fig.suptitle('A1  Quarterly static stress curves', fontweight='bold')
    fig.text(.1,.01,'Aave V3 | 13 quarter-end snapshots | factor-family 1:1 | 1 pp grid\nEligible debt is a stock, not realized liquidations. No uncertainty bands estimated.', fontsize=9)
    fig.subplots_adjust(bottom=.30,top=.9)
    save(fig,out,'A1_stress_13_quarters')
    write(out/'A1_source.csv',rows)

    # C1: each valued record is encoded through wallet-protocol and protocol-asset
    # links. The two links are representations of one exposure, not two claims.
    source=read(EXPOSURES)
    assert len(source)==198 and len({r['account'] for r in source})==69
    assert {r['block'] for r in source}=={'21762264'}
    valued=[r for r in source if r['priced']=='True']
    assert len(valued)==188
    wallets=sorted({r['account'] for r in source})
    symbols={r['token'].lower():r['symbol'] for r in read(TOKENS)}
    assets=sorted({r['asset'] for r in valued},key=lambda a:(symbols.get(a.lower(),a),a))
    protocols=['aave_v3','compound_v3_usdc','morpho_blue']
    debts=defaultdict(set)
    for r in valued:
        if r['kind']=='debt' and float(r['value_usd'])>0:
            debts[r['account']].add(r['protocol'])
    shared={w for w,p in debts.items() if len(p)>1}
    assert len(shared)==1
    shared_wallet=next(iter(shared))
    wallet_y={w:1-i/(len(wallets)-1) for i,w in enumerate(wallets)}
    # Put the shared wallet near the two protocols it links; no force layout claim.
    near=min(wallets,key=lambda w:abs(wallet_y[w]-.3))
    wallet_y[shared_wallet],wallet_y[near]=wallet_y[near],wallet_y[shared_wallet]
    asset_y={a:1-i/(len(assets)-1) for i,a in enumerate(assets)}
    protocol_y={'aave_v3':.86,'compound_v3_usdc':.5,'morpho_blue':.14}
    first=defaultdict(float);second=defaultdict(float)
    positive=0
    for r in valued:
        value=float(r['value_usd'])
        assert math.isfinite(value) and value>=0
        if value==0:continue
        positive+=1
        first[r['account'],r['protocol'],r['kind']]+=value
        second[r['protocol'],r['asset'],r['kind']]+=value
    colors={'debt':'#406882','collateral':'#9d8b78'}
    highlight='#c05c35'
    width_scale=max(max(first.values()),max(second.values()))
    fig,ax=plt.subplots(figsize=(10,9.2))
    for (w,p,k),v in sorted(first.items(),key=lambda x:(x[0][0] in shared,x[0][2]=='debt')):
        color=highlight if w in shared and k=='debt' else colors[k]
        ax.plot([0,1],[wallet_y[w],protocol_y[p]],color=color,
                linewidth=.25+2.2*math.sqrt(v/width_scale),alpha=.9 if w in shared else .32,zorder=4 if w in shared and k=='debt' else 1)
    for (p,a,k),v in second.items():
        ax.plot([1,2],[protocol_y[p],asset_y[a]],color=colors[k],
                linewidth=.25+2.2*math.sqrt(v/width_scale),alpha=.32,zorder=1)
    ax.scatter([0]*len(wallets),list(wallet_y.values()),s=12,color='#406882',zorder=3)
    ax.scatter([0],[wallet_y[shared_wallet]],s=75,color=highlight,zorder=4)
    for p,label in [('aave_v3','Aave V3'),('compound_v3_usdc','Comet USDC'),('morpho_blue','Morpho Blue')]:
        ax.scatter([1],[protocol_y[p]],s=210,color='#263b45',zorder=3)
        ax.text(1,protocol_y[p]+.025,label,ha='center',va='bottom',fontsize=10,fontweight='bold',bbox={'facecolor':'white','edgecolor':'none','alpha':.85})
    ax.scatter([2]*len(assets),list(asset_y.values()),s=18,color='#9d8b78',zorder=3)
    mapping=[]
    for n,a in enumerate(assets,1):
        label=symbols.get(a.lower()) or (a[:6]+'…'+a[-4:])
        ax.text(2.04,asset_y[a],label,va='center',fontsize=8)
        mapping.append({'node_id':f'T{n:02d}','asset':a,'symbol':symbols.get(a.lower(),''),'block':21762264})
    short=shared_wallet[:8]+'…'+shared_wallet[-5:]
    ax.annotate('Shared borrower\n'+short,xy=(0,wallet_y[shared_wallet]),xytext=(-.04,wallet_y[shared_wallet]-.07),ha='right',fontsize=9,color=highlight,
                arrowprops={'arrowstyle':'-','color':highlight})
    ax.text(0,1.05,'69 wallets',ha='center',fontweight='bold')
    ax.text(1,1.05,'3 protocols',ha='center',fontweight='bold')
    ax.text(2,1.05,'40 priced assets',ha='center',fontweight='bold')
    ax.set(xlim=(-.48,2.58),ylim=(-.03,1.1));ax.axis('off')
    ax.legend(handles=[Line2D([0],[0],color=colors['debt'],label='Debt'),Line2D([0],[0],color=colors['collateral'],label='Collateral'),Line2D([0],[0],color=highlight,label='Shared-borrower debt')],
              loc='upper center',bbox_to_anchor=(.5,-.015),ncol=3,frameon=False,fontsize=9)
    fig.suptitle('C1  Sampled exposure network at block 21,762,264',fontweight='bold',y=.99)
    fig.text(.06,.02,'188 priced records: 122 positive exposures shown as aggregated links; 66 zero values omitted.\n10 unpriced rows excluded. Link width scales with sqrt(USD); node sizes are fixed.\nOne exposure has two links: do not add their values. No causal or default-propagation interpretation.',fontsize=9)
    fig.subplots_adjust(bottom=.14,top=.95,left=.05,right=.98)
    save(fig,out,'C1_sampled_exposure_network')
    write(out/'C1_source_188_priced_records.csv',valued)
    write(out/'C1_asset_labels.csv',mapping)
    write(out/'C1_wallet_labels.csv',[{'wallet':w,'shared_debt_wallet':w in shared} for w in wallets])

    # D1: paired scenarios from the same frozen, stylized engine.
    rows=read(paths[1]);selected=[];fig,ax=plt.subplots(figsize=(8,5.2))
    for offset,case,label,color in [(-.18,'zero_impact_control','No price feedback','#889ca5'),(.18,'assumed_impact','Assumed price feedback','#c07852')]:
        group=sorted([r for r in rows if r['case']==case],key=lambda r:float(r['shock_fraction']))
        assert len(group)==3
        for r in group:
            assert float(r['close_factor'])==.5 and float(r['bonus_fraction'])==.05 and float(r['lt_shift'])==0
        vals=[float(r['repaid_usd'])/1e6 for r in group]
        bars=ax.bar([i+offset for i in range(3)],vals,width=.34,label=label,color=color)
        ax.bar_label(bars,labels=[f'{v:,.2f}' for v in vals],padding=4,fontsize=9)
        selected.extend(group)
    ax.set_xticks(range(3),['10%','20%','30%'])
    ax.set(xlabel='Joint ETH/BTC price decline',ylabel='Debt repaid in simulation (USD million)',ylim=(0,1500))
    ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.legend(frameon=False,loc='upper left')
    fig.suptitle('D1  Stylized cascade scenarios — not calibrated',fontweight='bold')
    fig.text(.1,.02,'Same snapshot; close factor 50%; bonus 5%; assumed depth USD 100m.\nDebt repaid is not liquidated collateral value or observed on-chain bad debt.',fontsize=9)
    fig.subplots_adjust(bottom=.23,top=.88)
    save(fig,out,'D1_cascade_stylized')
    write(out/'D1_source.csv',selected)

    assert all(digest(ROOT/p)==h for p,h in original.items()),'Source modified'
    audit={'inputs_sha256':original,'H1_quarters':quarters,'H1_points':len(read(out/'A1_source.csv')),
           'network_wallets':len(wallets),'network_priced_records':len(valued),'network_positive_records':positive,
           'network_unpriced_records':len(source)-len(valued),'network_shared_wallet':shared_wallet,
           'D1_scenarios':len(selected),'sources_unchanged':True}
    (out/'figure_provenance.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=Path(__file__).resolve().parent/'figures')
    build(parser.parse_args().out)
