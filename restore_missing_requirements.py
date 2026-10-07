import sqlite3
import json
from requirement_identity import compute_requirement_identity

conn = sqlite3.connect('data/metaforge_requirements.db')
conn.row_factory = sqlite3.Row

records_to_restore = [
    {
        'job_id': '2026/10/06-003',
        'req_date': '2026/10/06',
        'seq': 3,
        'client_jd_id': None,
        'created_at': '2026-10-06T01:48:17Z',
        'first_arrival_at': '2026-10-06T01:48:17Z',
        'demand_received_date': '2026-10-06',
        'receivedDateTime': '2026-10-06T01:48:17Z',
        'requirement_from': 'LTTS',
        'client_key': 'ltts',
        'job_title': 'PCB ECAD Engineer',
        'role_title': 'PCB ECAD Engineer',
        'number_of_positions': 4,
        'location': 'Bangalore/Pune',
        'work_location': 'Bangalore/Pune',
        'overall_experience': '8- 15 Years',
        'experience': '8- 15 Years',
        'overall_experience_min': 8,
        'overall_experience_max': 15,
        'monthly_budget': 150000,
        'budget': 'INR 1.5 L/M to 2 L/M',
        'budget_text': 'INR 1.5 L/M to 2 L/M',
        'budget_currency': 'INR',
        'job_status': 'open',
        'requirement_status': 'open',
        'notice_period': 'ONLY IMMEDIATE JOINERS REQUIRED',
        'qualification': "Bachelor's Degree or Diploma in Electronics and communications",
        'educational_qualifications': "Bachelor's Degree or Diploma in Electronics and communications",
        'mandatory_skills': [
            'Hands on Experience in High-Speed PCB Design [DDR 4/5, LPDDR, PCIe, MIPI 10 Gig+, Ethernet etc]',
            'Altium Design tool experience',
            'Multilayer PCB design',
            'Library Part Creation, Placement, Routing, DRC setting up and DRC error clearance',
            'Generation of Hype File for SI and PI analysis',
            'EMI/EMC Compliance'
        ],
        'skills': [
            'High-Speed PCB Design',
            'Altium Design tool',
            'Multilayer PCB design',
            'Library Part Creation',
            'Placement',
            'Routing',
            'DRC setting up',
            'DRC error clearance',
            'SI and PI analysis',
            'EMI/EMC Compliance'
        ],
        'subject': 'TPC - Requirement - EMB - PCB ECAD Engineer for Bangalore/Pune',
        'from': 'Kallol.Chakraborty@Ltts.com',
        'client_poc': 'Kallol.Chakraborty@Ltts.com',
        'client_lead_poc': 'Kallol.Chakraborty@Ltts.com',
        'to': 'Deepashree.Bc_ext@Ltts.com, Caroline.Anisha_ext@Ltts.com',
        'cc': 'Ashwini.Kudi@Ltts.com',
        'graphMessageId': 'AAMkADE3NDllMmZlLTU3NmUtNGI2MS1hZjA4LTEwNzAzZWZjYzUxOABGAAAAAABG8jimhHIeTrzzeDCLnQR9BwAIHnK_cnn0TIdFuplFGEzAAAAAAAEMAAAIHnK_cnn0TIdFuplFGEzAAAB-_z2oAAA=',
        'pipeline_extracted': True,
    },
    {
        'job_id': '2026/10/06-005',
        'req_date': '2026/10/06',
        'seq': 5,
        'client_jd_id': None,
        'created_at': '2026-10-06T01:50:17Z',
        'first_arrival_at': '2026-10-06T01:50:17Z',
        'demand_received_date': '2026-10-06',
        'receivedDateTime': '2026-10-06T01:50:17Z',
        'requirement_from': 'LTTS',
        'client_key': 'ltts',
        'job_title': 'Emulation Consultant',
        'role_title': 'Emulation Consultant',
        'number_of_positions': 3,
        'location': 'Bangalore',
        'work_location': 'Bangalore',
        'overall_experience': "5- 8 Years'",
        'experience': "5- 8 Years'",
        'overall_experience_min': 5,
        'overall_experience_max': 8,
        'monthly_budget': 140000,
        'budget': '140000',
        'budget_text': '140000',
        'budget_currency': 'INR',
        'job_status': 'open',
        'requirement_status': 'open',
        'notice_period': 'ONLY IMMEDIATE JOINERS REQUIRED',
        'mandatory_skills': [
            'Cadence Palladium flows',
            'Post Silicon debug experience',
            'Reproduction of Si issues on palladium',
            'Running/ porting SW tests on palladium',
            'Peripheral (uart, spi, i2c etc) protocol and debug knowledge',
            'Writing C test cases',
            'Writing tests cases in post Si bench (mostly Py controlled)'
        ],
        'skills': [
            'Cadence Palladium flows',
            'Post Silicon debug experience',
            'Reproduction of Si issues on palladium',
            'Running/ porting SW tests on palladium',
            'Peripheral protocol and debug knowledge',
            'Writing C test cases'
        ],
        'subject': 'TPC - Requirement - EMB - Emulation Consultant for Bangalore',
        'from': 'Kallol.Chakraborty@Ltts.com',
        'client_poc': 'Kallol.Chakraborty@Ltts.com',
        'client_lead_poc': 'Kallol.Chakraborty@Ltts.com',
        'to': 'Deepashree.Bc_ext@Ltts.com, Caroline.Anisha_ext@Ltts.com',
        'cc': 'Ashwini.Kudi@Ltts.com',
        'graphMessageId': 'AAMkADE3NDllMmZlLTU3NmUtNGI2MS1hZjA4LTEwNzAzZWZjYzUxOABGAAAAAABG8jimhHIeTrzzeDCLnQR9BwAIHnK_cnn0TIdFuplFGEzAAAAAAAEMAAAIHnK_cnn0TIdFuplFGEzAAAB-_z2pAAA=',
        'pipeline_extracted': True,
    },
    {
        'job_id': '2026/10/05-012',
        'req_date': '2026/10/05',
        'seq': 12,
        'client_jd_id': None,
        'created_at': '2026-10-05T07:46:29Z',
        'first_arrival_at': '2026-10-05T07:46:29Z',
        'demand_received_date': '2026-10-05',
        'receivedDateTime': '2026-10-05T07:46:29Z',
        'requirement_from': 'LTTS',
        'client_key': 'ltts',
        'job_title': 'Project Engineer',
        'role_title': 'Project Engineer',
        'number_of_positions': 1,
        'location': 'Aurangabad',
        'work_location': 'Aurangabad',
        'overall_experience': '6-8 Years',
        'experience': '6-8 Years',
        'overall_experience_min': 6,
        'overall_experience_max': 8,
        'monthly_budget': 140000,
        'budget': '140000 max',
        'budget_text': '140000 max',
        'budget_currency': 'INR',
        'job_status': 'open',
        'requirement_status': 'open',
        'domain': 'Medical Device industry or pharmaceutical or consumer or similar industry',
        'qualification': "Bachelor’s degree with minimum 6 to 8 years of experience in Engineering/Industrial/Electrical/Biotechnology Engineering (related stream).",
        'educational_qualifications': "Bachelor’s degree with minimum 6 to 8 years of experience in Engineering/Industrial/Electrical/Biotechnology Engineering (related stream).",
        'shift_timings': 'Candidates should be flexible for any shift based on project criteria.',
        'mandatory_skills': [
            'Medical Device industry',
            'manufacturing principles',
            'Six Sigma tools for process improvements',
            'Statistical Data Analysis',
            'critical path',
            'capacity modeling',
            'time and motion studies'
        ],
        'skills': [
            'Quality and Compliance',
            'Financial systems',
            'ROI Analysis',
            'Standard costs and planning values',
            'cycle time modelling covering critical path',
            'vacuum technology',
            'PLC programming',
            'electrical and mechanical engineering',
            'packaging process and package design'
        ],
        'subject': 'TPC - Requirement - SMS - Project Engineer and Process Engineer-Aurangabad',
        'from': 'Kallol.Chakraborty@Ltts.com',
        'client_poc': 'Kallol.Chakraborty@Ltts.com',
        'client_lead_poc': 'Kallol.Chakraborty@Ltts.com',
        'to': 'Arundhati.Rudagi_ext@Ltts.com, Pranati.Paul_ext@Ltts.com, Kv.Saisiri_ext@Ltts.com',
        'cc': 'Ashwini.Kudi@Ltts.com',
        'graphMessageId': 'AAMkADE3NDllMmZlLTU3NmUtNGI2MS1hZjA4LTEwNzAzZWZjYzUxOABGAAAAAABG8jimhHIeTrzzeDCLnQR9BwAIHnK_cnn0TIdFuplFGEzAAAAAAAEMAAAIHnK_cnn0TIdFuplFGEzAAAB-_z2MAAA=',
        'pipeline_extracted': True,
    },
    {
        'job_id': '2026/10/07-009',
        'req_date': '2026/10/07',
        'seq': 9,
        'client_jd_id': None,
        'created_at': '2026-10-07T07:27:03Z',
        'first_arrival_at': '2026-10-07T07:27:03Z',
        'demand_received_date': '2026-10-07',
        'receivedDateTime': '2026-10-07T07:27:03Z',
        'requirement_from': 'LTTS',
        'client_key': 'ltts',
        'job_title': 'Design Engineer',
        'role_title': 'Design Engineer',
        'number_of_positions': 2,
        'location': 'Pune',
        'work_location': 'Pune',
        'overall_experience': '4-5 Years',
        'experience': '4-5 Years',
        'overall_experience_min': 4,
        'overall_experience_max': 5,
        'monthly_budget': 100000,
        'budget': '100000',
        'budget_text': '100000',
        'budget_currency': 'INR',
        'job_status': 'open',
        'requirement_status': 'open',
        'notice_period': 'IMMEDIATE JOINERS',
        'mandatory_skills': [
            'PCB Hardware',
            'Design Engineer',
            'Medical Device'
        ],
        'skills': [
            'PCB Hardware',
            'Design Engineer',
            'Medical Device',
            'Altium / Mentor Xpedition / Similar',
            'SI basics and EMI/EMC practices'
        ],
        'subject': 'TPC - Requirement - Med tech - Design Engineer - Pune',
        'from': 'Kallol.Chakraborty@Ltts.com',
        'client_poc': 'Kallol.Chakraborty@Ltts.com',
        'client_lead_poc': 'Kallol.Chakraborty@Ltts.com',
        'to': 'Deepashree.Bc_ext@Ltts.com, Caroline.Anisha_ext@Ltts.com',
        'cc': 'Ashwini.Kudi@Ltts.com',
        'graphMessageId': 'AAMkADE3NDllMmZlLTU3NmUtNGI2MS1hZjA4LTEwNzAzZWZjYzUxOABGAAAAAABG8jimhHIeTrzzeDCLnQR9BwAIHnK_cnn0TIdFuplFGEzAAAAAAAEMAAAIHnK_cnn0TIdFuplFGEzAAAB-_z3JAAA=',
        'pipeline_extracted': True,
    }
]

for rec in records_to_restore:
    jid = rec['job_id']
    ident = compute_requirement_identity(
        client=rec['requirement_from'],
        client_jd_id=None,
        job_title=rec['job_title'],
        location=rec['location'],
        experience=rec['overall_experience'],
        mandatory_skills=rec['mandatory_skills']
    )
    rec['identity'] = ident
    
    # Insert or replace into metaforge_requirements
    conn.execute('''
        INSERT OR REPLACE INTO metaforge_requirements (
            job_id, payload_json, created_at, client_jd_id, req_date, seq, identity
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        jid,
        json.dumps(rec, ensure_ascii=False),
        rec['created_at'],
        None,
        rec['req_date'],
        rec['seq'],
        ident
    ))
    print(f'Restored {jid} ({rec["job_title"]}) with identity {ident}')

# Clean up former_job_id in canonical records
cleanups = [
    ('2026/09/20-004', '2026/10/05-012'),
    ('2026/09/23-019', '2026/10/06-003'),
    ('2026/09/23-021', '2026/10/06-005'),
    ('2026/09/11-040', '2026/10/07-009'),
]

for can_id, removed_id in cleanups:
    r = conn.execute('SELECT payload_json, former_job_id FROM metaforge_requirements WHERE job_id = ?', (can_id,)).fetchone()
    if r:
        p = json.loads(r['payload_json'])
        curr_formers = [x.strip() for x in (r['former_job_id'] or '').split(',') if x.strip() and x.strip() != removed_id]
        new_former = ','.join(curr_formers) if curr_formers else None
        p['former_job_id'] = new_former
        conn.execute('UPDATE metaforge_requirements SET payload_json = ?, former_job_id = ? WHERE job_id = ?', (
            json.dumps(p, ensure_ascii=False),
            new_former,
            can_id
        ))
        print(f'Cleaned former_job_id for {can_id}: {new_former}')

conn.commit()
conn.close()

# Also sync requirement_identity table in processed_messages.db
conn_pm = sqlite3.connect('data/processed_messages.db')
for rec in records_to_restore:
    conn_pm.execute('''
        INSERT OR REPLACE INTO requirement_identity (
            identity, client, client_jd_id, city, profile_json, state, original_record_ref, times_seen, first_seen, last_seen, last_graph_id, text_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        rec['identity'],
        'ltts',
        None,
        rec['location'],
        json.dumps(rec, ensure_ascii=False),
        'stored',
        rec['job_id'],
        1,
        rec['created_at'],
        rec['created_at'],
        rec['graphMessageId'],
        rec['identity']
    ))
conn_pm.commit()
conn_pm.close()
print('Successfully synced requirement_identity in processed_messages.db!')
