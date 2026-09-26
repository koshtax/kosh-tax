from utils.tax_calculator import calculate_tax

# 7th CPC Pay Matrix (Sorted for Increment calculation)
VALID_7TH_CPC_BASIC = sorted([
    18000, 18500, 19100, 19700, 20300, 20900, 21500, 22100, 22800, 23500, 24200, 24900, 
    25600, 26400, 27200, 28000, 28800, 29600, 30500, 31400, 32300, 33300, 34300, 35300, 
    36400, 37500, 38600, 39800, 41000, 42200, 43500, 44800, 46100, 47600, 49000, 50500, 
    52000, 53600, 55200, 56900, 58600, 60400, 62200, 64100, 66000, 68000, 70000, 72100, 
    74300, 76600, 79000, 81400, 83800, 86300, 88900, 91600, 94300, 97100, 100000, 103000, 
    106000, 109200, 112500, 115900, 119400, 123000, 126700, 130600, 134500, 138500, 142600, 
    146900, 151300, 155800, 160500, 165300, 170300, 175400, 180700, 186100, 191700, 197500, 
    203400, 209500, 215800, 222300
])

def get_next_increment(current_basic):
    for val in VALID_7TH_CPC_BASIC:
        if val > current_basic:
            return val
    return current_basic

def get_month_index(month_str):
    order = ['mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec', 'jan', 'feb']
    m_str = str(month_str).lower()
    for i, m in enumerate(order):
        if m in m_str:
            return i
    return -1


def complete_ledger(parsed_entries, base_user_data, active_fy):
    ledger = {}
    
    # 1. Structure existing entries
    for entry in parsed_entries:
        idx = get_month_index(entry.get('month_name', ''))
        if idx != -1:
            entry['source_type'] = entry.get('source_type', 'ACTUAL')
            # Ensure TA and Others exist safely
            entry['ta'] = float(entry.get('ta', 0.0))
            entry['others'] = float(entry.get('others', 0.0))
            ledger[idx] = entry

    def get_val(idx, key, default=0.0):
        return float(ledger[idx].get(key, default)) if idx in ledger else default

    # 2. AUTO-GENERATE JANUARY (Index 10)
    # Sirf tab generate hoga agar January missing hai aur December maujood hai
    if 10 not in ledger and 9 in ledger:
        june_basic = get_val(3, 'basic')
        july_basic = get_val(4, 'basic')
        dec_basic = get_val(9, 'basic')
        
        jan_basic = dec_basic
        # Rule: Increment if June Basic == July Basic
        if june_basic > 0 and july_basic > 0 and june_basic == july_basic:
            jan_basic = get_next_increment(dec_basic)

        # Proportional DA & HRA based on December's rules
        da_pct = get_val(9, 'da') / dec_basic if dec_basic > 0 else 0
        hra_pct = get_val(9, 'hra') / dec_basic if dec_basic > 0 else 0

        jan_da = round(jan_basic * da_pct)
        jan_hra = round(jan_basic * hra_pct)

        jan_gross = jan_basic + jan_da + jan_hra + get_val(9, 'medical') + get_val(9, 'ta') + get_val(9, 'others')

        ledger[10] = {
            'month_name': 'January',
            'basic': jan_basic,
            'da': jan_da,
            'hra': jan_hra,
            'ta': get_val(9, 'ta'),
            'medical': get_val(9, 'medical'),
            'others': get_val(9, 'others'),
            'gross': jan_gross,
            'gpf': get_val(9, 'gpf'),
            'ptax': get_val(9, 'ptax'),
            'tds': get_val(9, 'tds'), # Usually carries forward before Feb reconciliation
            'net': jan_gross - (get_val(9, 'gpf') + get_val(9, 'ptax') + get_val(9, 'tds')),
            'source_type': 'GENERATED'
        }

    # 3. AUTO-GENERATE FEBRUARY & TDS RECONCILIATION (Index 11)
    # Sirf tab generate hoga agar February missing hai aur January maujood hai
    if 11 not in ledger and 10 in ledger:
        feb_basic = get_val(10, 'basic')
        feb_da = get_val(10, 'da')
        feb_hra = get_val(10, 'hra')
        feb_gross = feb_basic + feb_da + feb_hra + get_val(10, 'medical') + get_val(10, 'ta') + get_val(10, 'others')
        
        # Calculate Total Annual Gross using ALL months (March to Feb)
        total_annual_gross = sum(get_val(i, 'gross') for i in range(11)) + feb_gross
        
        # Call Authoritative Tax Engine
        temp_user_data = base_user_data.copy()
        temp_user_data['gross'] = total_annual_gross
        tax_results = calculate_tax(temp_user_data, active_fy)
        final_tax_liability = tax_results.get('total_tax', 0)
        
        # Calculate TDS already deducted (March to Jan)
        tds_deducted_so_far = sum(get_val(i, 'tds') for i in range(11))
        
        # Balancing Figure for February TDS
        feb_tds = max(0.0, final_tax_liability - tds_deducted_so_far)
        
        ledger[11] = {
            'month_name': 'February',
            'basic': feb_basic,
            'da': feb_da,
            'hra': feb_hra,
            'ta': get_val(10, 'ta'),
            'medical': get_val(10, 'medical'),
            'others': get_val(10, 'others'),
            'gross': feb_gross,
            'gpf': get_val(10, 'gpf'),
            'ptax': get_val(10, 'ptax'),
            'tds': feb_tds,
            'net': feb_gross - (get_val(10, 'gpf') + get_val(10, 'ptax') + feb_tds),
            'source_type': 'GENERATED'
        }

    # 4. Construct Final Sorted Array
    final_ledger = []
    month_names = ['March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December', 'January', 'February']
    for i in range(12):
        if i in ledger:
            ledger[i]['month_name'] = month_names[i]
            final_ledger.append(ledger[i])
            
    return final_ledger
