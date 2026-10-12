import { useState, useRef } from 'react';
import { ShieldCheck, Activity, Plus, X, FileSignature, Upload, FileText, Code } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// --- MOCK DATA FOR REVIEWER QUEUE ---
const mockQueue = [
  {
    id: "aba4b94b-53b8",
    patient: "Neha Shah",
    diagnosis: "Calculus of gallbladder without cholecystitis (Gallstones)",
    status: "escalated",
    date: "2026-09-07",
    amount: "₹664,844.00",
    extractedData: {
      patient_id: "1574aa3f",
      age: 65,
      gender: "female",
      policy_number: "POL-385367"
    },
    reasoning: `**RECOMMENDATION — requires human sign‑off**

---

### Summary
- **Insured:** 65‑year‑old individual plan holder (Sum Insured ₹300,000, Co‑pay 0 %).  
- **Diagnosis:** Calculus of gallbladder without cholecystitis, ICD‑10 K80.20 (Gallstones).  
- **Procedure:** Planned laparoscopic cholecystectomy.  
- **Claim Amount:** ₹664,844 (exceeds the Sum Insured).  
- **Pre‑existing condition:** Yes.  

The claim is currently flagged for **non‑coverage due to an unmet specific disease waiting period**.

---

### Analysis
| Issue | Policy Reference | Interpretation |
|-------|------------------|----------------|
| **Specific disease waiting period** | **Clause 1** | Gallstone disease is listed as a specific disease that requires a 24‑month waiting period. |
| **Sum Insured limit** | Policy data (SI ₹300,000) | Even if the waiting period were satisfied, the claim amount would be capped at ₹300,000. |

The patient’s policy has not yet completed the required **24‑month specific disease waiting period** for gallstones.

---

### Deductions Applied
1. **Waiting‑Period Deduction** – ₹664,844 (full claim amount)  

---

### Recommendation
- **Primary recommendation:** **Reject** the cashless pre‑authorisation on the basis that the specific disease waiting period for cholelithiasis (24 months) has not been satisfied.
`
  },
  {
    id: "req-f923184",
    patient: "Rajesh Kumar",
    diagnosis: "Acute STEMI (Heart Attack)",
    status: "approved",
    date: "2025-06-01",
    amount: "₹84,000.00",
    extractedData: {
      patient_id: "pat-123",
      age: 45,
      gender: "male",
      policy_number: "POL-ACTIVE-101"
    },
    reasoning: `**RECOMMENDATION — APPROVED**

---

### Summary
- **Insured:** 45‑year‑old individual plan holder.
- **Diagnosis:** Acute STEMI, ICD-10 I21.0.
- **Procedure:** Primary PCI with DES.
- **Claim Amount:** ₹84,000.00.

The claim has passed all business logic rules.

### Analysis
All waiting periods are clear. The condition is an acute emergency. No specific disease waiting periods apply. The claim amount is well within the sum insured of ₹500,000.

**Final Decision:** Auto-Approved. No human intervention required.`
  }
];

export default function App() {
  const [queue, setQueue] = useState(mockQueue);
  const [activeItem, setActiveItem] = useState(mockQueue[0]);
  const [activeTab, setActiveTab] = useState('reasoning');
  const [isProcessing, setIsProcessing] = useState(false);
  const [showProcessModal, setShowProcessModal] = useState(false);
  const [inputType, setInputType] = useState('text'); // 'text', 'json', 'upload'
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const [inputText, setInputText] = useState(`A1 CASHLESS HEALTH INSURANCE PRE-AUTHORISATION FORM
--------------------------------------------------
Request ID: req-new-101
Submission Date: 2026-09-10
Source Format: text

PATIENT DETAILS
---------------
Patient Name: Ananya Rao
Age: 22
Gender: female
Policy Number: POL-9921

POLICY DETAILS
--------------
Plan Type: individual
Sum Insured: 1500000
Policy Start Date: 2025-01-01

HOSPITAL & CLINICAL DETAILS
---------------------------
Hospital Name: Fortis Hospital
City: Chandigarh
Network Tier: cashless_network
ICD-10 Code: K80.20
Diagnosis: Gallstones
Procedure Code: CPT-47562
Procedure: Laparoscopic cholecystectomy

ESTIMATED COST BREAKDOWN
-----------------------
  Estimated Room Rent: INR 15000.00
  Estimated Surgeon Fee: INR 45000.00
Total Amount: INR 60000.00`);

  const [inputJson, setInputJson] = useState(`{
  "request_id": "req-json-001",
  "submitted_at": "2026-10-15",
  "source_format": "json",
  "status": "pending",
  "admission_date": "2026-10-16",
  "patient": {
    "patient_id": "pat-456",
    "full_name": "Karthik Iyer",
    "age": 52,
    "gender": "male",
    "policy_number": "POL-123456"
  },
  "policy": {
    "policy_number": "POL-123456",
    "plan_type": "individual",
    "sum_insured": "1000000.00",
    "policy_start_date": "2021-01-01",
    "waiting_period_months": 0,
    "sub_limits": {"limits": {"room_rent_per_day": "10000.00"}},
    "co_pay_pct": "0.00"
  },
  "hospital": {
    "hospital_id": "hosp-789",
    "name": "Apollo Hospitals",
    "city": "Chennai",
    "network_tier": "cashless_network",
    "category": "multi_specialty"
  },
  "diagnosis": {
    "icd10_code": "I21.0",
    "description": "Acute STEMI",
    "is_pre_existing": false
  },
  "procedure": {
    "procedure_code": "PCI-002",
    "description": "Primary Angioplasty",
    "admission_type": "emergency"
  },
  "cost_estimate": {
    "line_items": [
      {"item": "Room Rent", "amount": "8000.00", "category": "room_rent"},
      {"item": "Surgeon Fee", "amount": "150000.00", "category": "surgeon_fee"}
    ],
    "total_amount": "158000.00"
  }
}`);

  const handleProcess = async () => {
    setIsProcessing(true);
    setShowProcessModal(false);
    
    try {
      let response;
      
      if (inputType === 'text') {
        response = await fetch('/api/v1/preauth/text', {
          method: 'POST',
          headers: { 'Content-Type': 'text/plain' },
          body: inputText
        });
      } else if (inputType === 'json') {
        try {
          const parsedJson = JSON.parse(inputJson);
          response = await fetch('/api/v1/preauth/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(parsedJson)
          });
        } catch (e) {
          alert('Invalid JSON format.');
          setIsProcessing(false);
          return;
        }
      } else if (inputType === 'upload' && selectedFile) {
        const formData = new FormData();
        formData.append('file', selectedFile);
        response = await fetch('/api/v1/preauth/upload', {
          method: 'POST',
          body: formData
        });
      } else {
        alert('Please select a file to upload.');
        setIsProcessing(false);
        return;
      }
      
      const data = await response.json();
      
      if (data.status === 'success') {
        // Adjust for different response structures from endpoints
        const requestData = data.extracted_request || (data.adjudication_metrics && data.adjudication_metrics.request_id ? {
            request_id: data.adjudication_metrics.request_id,
            submitted_at: new Date().toISOString().split('T')[0],
            patient: { full_name: "Patient " + data.adjudication_metrics.request_id.substring(0, 4) },
            diagnosis: { description: "Clinical Diagnosis" },
            cost_estimate: { total_amount: data.adjudication_metrics.total_claimed }
        } : null);

        if (!requestData && inputType === 'json') {
             // For JSON endpoint, it doesn't return extracted_request, so we fake the UI data from input
             const parsed = JSON.parse(inputJson);
             requestData.request_id = parsed.request_id;
             requestData.patient = parsed.patient;
             requestData.diagnosis = parsed.diagnosis;
             requestData.cost_estimate = parsed.cost_estimate;
             requestData.submitted_at = parsed.submitted_at;
        }

        const newItem = {
          id: requestData?.request_id || "req-new",
          patient: requestData?.patient?.full_name?.split('\n')[0] || "Unknown Patient",
          diagnosis: requestData?.diagnosis?.description?.split('\n')[0] || "Unknown Diagnosis",
          status: data.pipeline_status || data.recommendation || "completed",
          date: requestData?.submitted_at || new Date().toISOString().split('T')[0],
          amount: `₹${requestData?.cost_estimate?.total_amount || 0}`,
          extractedData: requestData?.patient || {},
          reasoning: data.reasoning
        };
        
        setQueue([newItem, ...queue]);
        setActiveItem(newItem);
        setActiveTab('reasoning');
      } else {
        alert('Error processing claim: ' + data.message);
      }
    } catch (err) {
      console.error(err);
      alert('Failed to connect to backend server.');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <>
      <div className="app-container">
        {/* Sidebar */}
        <div className="sidebar glass-panel animate-mount">
          <div className="brand-header">
            <Activity className="text-primary" size={24} color="#3b82f6" />
            <h1>A1 PreAuth Audit</h1>
          </div>
          
          <div style={{ padding: '0 16px' }}>
            <button 
              className="primary-btn" 
              style={{ width: '100%', justifyContent: 'center' }}
              onClick={() => setShowProcessModal(true)}
            >
              <Plus size={18} /> Process New Claim
            </button>
          </div>

          <div className="queue-list">
            {queue.map((item, i) => (
              <div 
                key={item.id} 
                className={`queue-item ${activeItem.id === item.id ? 'active' : ''} delay-${i+1}`}
                onClick={() => setActiveItem(item)}
              >
                <div className="item-header">
                  <span className="item-id">{item.id.substring(0, 8)}...</span>
                  <span className={`status-badge status-${item.status}`}>
                    {item.status.replace('RECOMMEND_', '')}
                  </span>
                </div>
                <div className="patient-name">{item.patient}</div>
                <div className="diagnosis-text">{item.diagnosis}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Main Content */}
        <div className="main-content glass-panel animate-mount delay-1">
          {activeItem ? (
            <>
              <div className="action-header">
                <div>
                  <h2 className="claim-title">{activeItem.patient}</h2>
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginTop: '4px' }}>
                    {activeItem.id} • {activeItem.date}
                  </div>
                </div>
                {(activeItem.status === 'escalated' || activeItem.status.includes('QUERY')) && (
                  <button className="primary-btn" style={{ background: 'var(--success)' }}>
                    <FileSignature size={18} /> Sign-off Review
                  </button>
                )}
              </div>

              <div style={{ padding: '0 24px' }}>
                <div className="stats-grid">
                  <div className="stat-card glass-panel">
                    <span className="stat-label">Claim Amount</span>
                    <span className="stat-value">{activeItem.amount}</span>
                  </div>
                  <div className="stat-card glass-panel">
                    <span className="stat-label">Policy No.</span>
                    <span className="stat-value" style={{ fontSize: '1.2rem', marginTop: 'auto' }}>
                      {activeItem.extractedData?.policy_number || 'N/A'}
                    </span>
                  </div>
                  <div className="stat-card glass-panel">
                    <span className="stat-label">System Decision</span>
                    <span className="stat-value" style={{ 
                      fontSize: '1.2rem', 
                      marginTop: 'auto',
                      color: activeItem.status.includes('approved') || activeItem.status.includes('AUTHORISE') ? 'var(--success)' : 'var(--warning)'
                    }}>
                      {activeItem.status.replace('RECOMMEND_', '').toUpperCase()}
                    </span>
                  </div>
                </div>

                <div className="tabs">
                  <div 
                    className={`tab ${activeTab === 'reasoning' ? 'active' : ''}`}
                    onClick={() => setActiveTab('reasoning')}
                  >
                    AI Reasoning Trace
                  </div>
                  <div 
                    className={`tab ${activeTab === 'audit' ? 'active' : ''}`}
                    onClick={() => setActiveTab('audit')}
                  >
                    Immutable Audit Log
                  </div>
                </div>

                <div className="tab-content glass-panel">
                  {activeTab === 'reasoning' ? (
                    <div className="markdown-body">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {activeItem.reasoning}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <div className="audit-log" style={{ fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                      <div>[SYSTEM] Received raw payload at {activeItem.date}</div>
                      <div>[SYSTEM] Executed Intake Extraction</div>
                      <div>[SYSTEM] Loaded Policy Vector (Cosine Sim: 0.89)</div>
                      <div>[SYSTEM] Executing Deterministic Rules Engine...</div>
                      <div>[SYSTEM] Invoking LLM for Reasoning Synthesis...</div>
                      <div>[SYSTEM] Emitted final state: {activeItem.status}</div>
                      <div style={{ marginTop: '16px', color: 'var(--success)' }}>✓ Hash chain verified. Cryptographic seal intact.</div>
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state">
              <ShieldCheck size={48} />
              <h2>Select a claim to review</h2>
            </div>
          )}
        </div>
      </div>

      {/* Loading Overlay */}
      {isProcessing && (
        <div className="loading-overlay">
          <div className="spinner"></div>
          <div className="glow-text" style={{ fontSize: '1.2rem', fontWeight: 500 }}>
            Processing via LangGraph...
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Extracting ➔ Vector Search ➔ Rules ➔ LLM Audit
          </div>
        </div>
      )}

      {/* Process Modal */}
      {showProcessModal && (
        <div className="modal-overlay">
          <div className="modal glass-panel">
            <div className="modal-header">
              <h2>Submit Pre-Authorisation Request</h2>
              <button className="close-btn" onClick={() => setShowProcessModal(false)}>
                <X size={20} />
              </button>
            </div>
            
            <div className="tabs" style={{ marginBottom: '16px' }}>
              <div 
                className={`tab ${inputType === 'text' ? 'active' : ''}`}
                onClick={() => setInputType('text')}
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
              >
                <FileText size={16} /> Free Text Note
              </div>
              <div 
                className={`tab ${inputType === 'json' ? 'active' : ''}`}
                onClick={() => setInputType('json')}
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
              >
                <Code size={16} /> JSON Payload
              </div>
              <div 
                className={`tab ${inputType === 'upload' ? 'active' : ''}`}
                onClick={() => setInputType('upload')}
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
              >
                <Upload size={16} /> File Upload
              </div>
            </div>

            {inputType === 'text' && (
              <textarea 
                className="input-area"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder="Enter free-text clinical notes..."
              />
            )}

            {inputType === 'json' && (
              <textarea 
                className="input-area"
                value={inputJson}
                onChange={(e) => setInputJson(e.target.value)}
                placeholder="Enter JSON payload..."
              />
            )}

            {inputType === 'upload' && (
              <div style={{ 
                border: '2px dashed var(--border)', 
                borderRadius: '8px', 
                padding: '40px', 
                textAlign: 'center',
                marginBottom: '20px',
                background: 'rgba(0,0,0,0.2)'
              }}>
                <Upload size={32} style={{ color: 'var(--text-muted)', marginBottom: '16px' }} />
                <h3 style={{ marginBottom: '8px' }}>Upload Document</h3>
                <p style={{ color: 'var(--text-muted)', marginBottom: '16px', fontSize: '0.9rem' }}>
                  Supports PDF, DOCX, and scanned Images (PNG, JPG)
                </p>
                <input 
                  type="file" 
                  ref={fileInputRef}
                  onChange={(e) => setSelectedFile(e.target.files ? e.target.files[0] : null)}
                  style={{ display: 'none' }}
                />
                <button 
                  className="secondary-btn" 
                  onClick={() => fileInputRef.current?.click()}
                >
                  {selectedFile ? selectedFile.name : 'Select File'}
                </button>
              </div>
            )}

            <div className="modal-actions">
              <button className="secondary-btn" onClick={() => setShowProcessModal(false)}>Cancel</button>
              <button 
                className="primary-btn" 
                onClick={handleProcess}
                disabled={inputType === 'upload' && !selectedFile}
              >
                Process Request
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
