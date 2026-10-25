"""Presentation labels only; legacy dataset/module names are stable."""
LABELS={
 'H1':{'topic':'Price shocks and borrower vulnerability','module':'h1'},
 'H2':{'topic':'Matched liquidation concentration and Comet measurement','module':'h2'},
 'H3':{'topic':'Temporal clustering and conditional self-excitation','module':'h4','previous_label':'H4'},
}

def current_report_labels(text):
    return text.replace('H4','H3')
