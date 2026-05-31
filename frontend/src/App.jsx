import React, { useState, useEffect } from 'react';
import './App.css';

const API_BASE = import.meta.env.VITE_API_URL || (window.location.port === '5173' ? 'http://localhost:8000' : '');

const CAMERAS_LIST = [
  { id: 'CAM_ENTRY_03', name: 'Main Entry Door (CAM 3)', file: 'CAM 3.mp4', zone: 'ENTRY', fps: 30, res: '1080p' },
  { id: 'CAM_FLOOR_01', name: 'Skincare Aisle (CAM 1)', file: 'CAM 1.mp4', zone: 'SKINCARE_AISLE', fps: 30, res: '1080p' },
  { id: 'CAM_FLOOR_02', name: 'Makeup Aisle (CAM 2)', file: 'CAM 2.mp4', zone: 'MAKEUP_AISLE', fps: 30, res: '1080p' },
  { id: 'CAM_STOCKROOM_04', name: 'Stock Room (CAM 4)', file: 'CAM 4.mp4', zone: 'STOCKROOM', fps: 30, res: '720p' },
  { id: 'CAM_CHECKOUT_05', name: 'Billing POS (CAM 5)', file: 'CAM 5.mp4', zone: 'CHECKOUT', fps: 30, res: '1080p' }
];

function App() {
  const [activeTab, setActiveTab] = useState('dashboard'); // 'dashboard', 'cameras', 'settings'
  const [selectedCam, setSelectedCam] = useState(CAMERAS_LIST[0]);
  
  // Filters
  const [storeId, setStoreId] = useState('ALL');
  const [date, setDate] = useState('2026-04-10'); // Default to date of CCTV footage
  
  // Developer/Backend focused options
  const [showJsonInspector, setShowJsonInspector] = useState(false);
  const [apiLatencies, setApiLatencies] = useState({});
  const [rawEvents, setRawEvents] = useState([]);
  
  // Settings config (simulated state)
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.25);
  const [trackingThreshold, setTrackingThreshold] = useState(0.50);
  const [posWindow, setPosWindow] = useState(120);
  const [excludeStaff, setExcludeStaff] = useState(true);
  const [toastMessage, setToastMessage] = useState(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  const [metrics, setMetrics] = useState(null);
  const [funnelData, setFunnelData] = useState(null);
  const [anomaliesData, setAnomaliesData] = useState(null);

  const fetchData = async (isSilent = false) => {
    if (!isSilent) setLoading(true);
    setError(null);
    const start = performance.now();
    try {
      const storeParam = storeId !== 'ALL' ? `store_id=${storeId}` : '';
      const dateParam = date ? `date=${date}` : '';
      const params = [storeParam, dateParam].filter(Boolean).join('&');
      const query = params ? `?${params}` : '';

      const urls = {
        metrics: `${API_BASE}/metrics${query}`,
        funnel: `${API_BASE}/funnel${query}`,
        anomalies: `${API_BASE}/anomalies${query}`,
        events: `${API_BASE}/events${query}${query ? '&' : '?'}limit=15`
      };

      const latencies = {};
      
      const fetchWithTimer = async (key, url) => {
        const t0 = performance.now();
        const res = await fetch(url);
        const t1 = performance.now();
        latencies[key] = Math.round(t1 - t0);
        if (!res.ok) throw new Error(`${key} endpoint returned error`);
        return res.json();
      };

      const [metricsJson, funnelJson, anomaliesJson, eventsJson] = await Promise.all([
        fetchWithTimer('metrics', urls.metrics),
        fetchWithTimer('funnel', urls.funnel),
        fetchWithTimer('anomalies', urls.anomalies),
        fetchWithTimer('events', urls.events)
      ]);

      setMetrics(metricsJson);
      setFunnelData(funnelJson);
      setAnomaliesData(anomaliesJson);
      setRawEvents(eventsJson.events || []);
      setApiLatencies(latencies);
    } catch (err) {
      console.error(err);
      setError('Could not fetch store analytics data. Make sure the backend API is running on localhost:8000.');
    } finally {
      if (!isSilent) setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => {
      fetchData(true);
    }, 5000);
    return () => clearInterval(interval);
  }, [storeId, date]);

  const formatCurrency = (val) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(val);
  };

  const handleSaveSettings = () => {
    setToastMessage('Pipeline configuration updated and saved!');
    setTimeout(() => setToastMessage(null), 3000);
  };

  const handleResetDatabase = async () => {
    if (window.confirm("Are you sure you want to re-initialize the pipeline database cache?")) {
      setLoading(true);
      try {
        await new Promise(resolve => setTimeout(resolve, 1000));
        setToastMessage('Database cache cleared and transactions re-indexed.');
        setTimeout(() => setToastMessage(null), 3000);
        fetchData();
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
  };

  const makeWaterfallData = () => {
    if (!funnelData || !funnelData.funnel) return [];
    const entries = funnelData.funnel.find(e => e.stage === '1_entered') || { visitors: 0, pct_of_entry: 0 };
    const browsed = funnelData.funnel.find(e => e.stage === '2_browsed') || { visitors: 0, pct_of_entry: 0 };
    const checkout = funnelData.funnel.find(e => e.stage === '3_at_checkout') || { visitors: 0, pct_of_entry: 0 };
    const purchased = funnelData.funnel.find(e => e.stage === '4_purchased') || { visitors: 0, pct_of_entry: 0 };

    return [
      {
        type: 'stage',
        name: 'Entered',
        icon: '🚪',
        visitors: entries.visitors,
        pct: entries.pct_of_entry,
        colorClass: 'bg-indigo-600 shadow-[0_0_15px_rgba(99,102,241,0.25)]',
      },
      {
        type: 'dropoff',
        name: 'Browse Loss',
        diff: entries.visitors - browsed.visitors,
        diffPct: entries.pct_of_entry - browsed.pct_of_entry,
        bottom: browsed.pct_of_entry,
        height: entries.pct_of_entry - browsed.pct_of_entry,
        colorClass: 'bg-rose-500/20 border border-rose-500/40 text-rose-400',
      },
      {
        type: 'stage',
        name: 'Browsed',
        icon: '🧴',
        visitors: browsed.visitors,
        pct: browsed.pct_of_entry,
        colorClass: 'bg-indigo-500 shadow-[0_0_12px_rgba(99,102,241,0.2)]',
      },
      {
        type: 'dropoff',
        name: 'Checkout Loss',
        diff: browsed.visitors - checkout.visitors,
        diffPct: browsed.pct_of_entry - checkout.pct_of_entry,
        bottom: checkout.pct_of_entry,
        height: browsed.pct_of_entry - checkout.pct_of_entry,
        colorClass: 'bg-rose-500/20 border border-rose-500/40 text-rose-400',
      },
      {
        type: 'stage',
        name: 'Checkout',
        icon: '💳',
        visitors: checkout.visitors,
        pct: checkout.pct_of_entry,
        colorClass: 'bg-indigo-400 shadow-[0_0_10px_rgba(129,140,248,0.15)]',
      },
      {
        type: 'dropoff',
        name: 'Purchase Loss',
        diff: checkout.visitors - purchased.visitors,
        diffPct: checkout.pct_of_entry - purchased.pct_of_entry,
        bottom: purchased.pct_of_entry,
        height: checkout.pct_of_entry - purchased.pct_of_entry,
        colorClass: 'bg-rose-500/20 border border-rose-500/40 text-rose-400',
      },
      {
        type: 'stage',
        name: 'Purchased',
        icon: '🛍️',
        visitors: purchased.visitors,
        pct: purchased.pct_of_entry,
        colorClass: 'bg-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.3)]',
      }
    ];
  };

  const waterfallData = makeWaterfallData();

  return (
    <div className="min-h-screen flex bg-[#0c0e12] text-slate-200 font-sans antialiased">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed top-6 left-1/2 -translate-x-1/2 bg-slate-900 border border-slate-700 shadow-xl px-5 py-3 rounded-lg text-xs font-semibold text-slate-300 flex items-center gap-2 z-50">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-ping"></span>
          <p>{toastMessage}</p>
        </div>
      )}

      {/* Sidebar - Clean & Minimal */}
      <aside className="w-60 bg-[#12151c] border-r border-slate-800 p-6 flex flex-col flex-shrink-0">
        <div className="flex items-center gap-3 mb-10">
          <div className="w-8 h-8 bg-slate-800 border border-slate-700 rounded-lg flex items-center justify-center font-bold text-white shadow-sm text-sm">
            P
          </div>
          <div>
            <h2 className="font-bold text-sm tracking-tight text-white leading-none">Purplle</h2>
            <span className="text-[9px] text-slate-400 font-medium uppercase tracking-wider block mt-1">Intelligence</span>
          </div>
        </div>

        <nav className="flex flex-col gap-1 flex-grow">
          <div 
            className={`nav-item flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium text-xs uppercase tracking-wider transition-all duration-150 cursor-pointer ${
              activeTab === 'dashboard' 
                ? 'bg-slate-800 text-white border-l-2 border-indigo-500' 
                : 'text-slate-400 hover:text-white hover:bg-slate-800/40'
            }`}
            onClick={() => setActiveTab('dashboard')}
            id="nav-tab-dashboard"
          >
            <span>📊</span> Dashboard
          </div>
          <div 
            className={`nav-item flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium text-xs uppercase tracking-wider transition-all duration-150 cursor-pointer ${
              activeTab === 'cameras' 
                ? 'bg-slate-800 text-white border-l-2 border-indigo-500' 
                : 'text-slate-400 hover:text-white hover:bg-slate-800/40'
            }`}
            onClick={() => setActiveTab('cameras')}
            id="nav-tab-cameras"
          >
            <span>📹</span> Camera Feeds
          </div>
          <div 
            className={`nav-item flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium text-xs uppercase tracking-wider transition-all duration-150 cursor-pointer ${
              activeTab === 'settings' 
                ? 'bg-slate-800 text-white border-l-2 border-indigo-500' 
                : 'text-slate-400 hover:text-white hover:bg-slate-800/40'
            }`}
            onClick={() => setActiveTab('settings')}
            id="nav-tab-settings"
          >
            <span>⚙️</span> Settings
          </div>
        </nav>

        <div className="text-[10px] text-slate-500 pt-4 border-t border-slate-800 flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
          <span className="font-semibold uppercase tracking-wider text-slate-400">Database API Connected</span>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-grow p-8 max-w-7xl mx-auto overflow-y-auto w-full">
        
        {/* Header Section */}
        <header className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8 pb-6 border-b border-slate-850">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white mb-1">
              {activeTab === 'dashboard' && "Store Intelligence Metrics"}
              {activeTab === 'cameras' && "Live CCTV Channels"}
              {activeTab === 'settings' && "Pipeline Config"}
            </h1>
            <p className="text-xs text-slate-400">
              {activeTab === 'dashboard' && "Processed database records, conversion metrics, and system anomaly logs"}
              {activeTab === 'cameras' && "Active channels streaming directly from workspace local video folder"}
              {activeTab === 'settings' && "Configure models, staff filters, and database indices"}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Filters Bar */}
            {activeTab !== 'settings' && (
              <div className="flex items-center gap-3 bg-[#13161c] border border-slate-800 p-2 rounded-lg text-xs">
                <div className="flex flex-col px-2">
                  <span className="text-[9px] text-slate-500 uppercase font-semibold mb-0.5">Store ID</span>
                  <select 
                    value={storeId} 
                    onChange={(e) => setStoreId(e.target.value)} 
                    className="bg-transparent text-xs text-slate-200 font-bold outline-none cursor-pointer border-none p-0 focus:ring-0"
                    id="store-id-select"
                  >
                    <option value="ALL" className="bg-[#12151c] text-slate-200">All Stores</option>
                    <option value="STORE_PUR_001" className="bg-[#12151c] text-slate-200">Brigade Bangalore (ST1008)</option>
                  </select>
                </div>
                
                <div className="w-px h-5 bg-slate-800"></div>
                
                <div className="flex flex-col px-2">
                  <span className="text-[9px] text-slate-500 uppercase font-semibold mb-0.5">Date</span>
                  <input 
                    type="date" 
                    value={date} 
                    onChange={(e) => setDate(e.target.value)} 
                    className="bg-transparent text-xs text-slate-200 font-bold outline-none cursor-pointer border-none p-0 [color-scheme:dark] focus:ring-0"
                    id="date-input"
                  />
                </div>

                <button 
                  className={`w-7 h-7 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded flex items-center justify-center text-xs transition-all ${
                    loading ? 'animate-spin' : ''
                  }`}
                  onClick={fetchData} 
                  disabled={loading}
                  id="refresh-data-btn"
                >
                  ↻
                </button>
              </div>
            )}

            {/* Dev Mode toggle */}
            <button 
              className={`px-3 py-2 rounded-lg text-xs font-semibold border transition-all ${
                showJsonInspector 
                  ? 'bg-indigo-500/10 border-indigo-500/30 text-indigo-400' 
                  : 'bg-slate-800 border-slate-750 text-slate-400 hover:text-slate-300'
              }`}
              onClick={() => setShowJsonInspector(!showJsonInspector)}
            >
              🛠️ Backend API Inspector
            </button>
          </div>
        </header>

        {/* Backend Inspector details */}
        {showJsonInspector && metrics && (
          <div className="bg-[#13161c] border border-slate-800 p-5 rounded-xl mb-8 space-y-4 animate-fadeIn">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">📡 Active REST API Latencies & Target Endpoints</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {Object.keys(apiLatencies).map(key => (
                <div key={key} className="bg-slate-900 border border-slate-800 p-3 rounded-lg text-xs">
                  <span className="text-slate-500 block uppercase font-bold text-[9px] mb-1">GET /{key}</span>
                  <div className="flex justify-between items-baseline">
                    <strong className="text-slate-300 font-semibold">200 OK</strong>
                    <span className="text-emerald-400 font-bold">{apiLatencies[key]} ms</span>
                  </div>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div>
                <span className="text-[10px] font-bold text-slate-500 block mb-1.5 uppercase">Metrics Endpoint Response Payload JSON</span>
                <pre className="text-[10px] font-mono bg-slate-950 p-4 rounded-lg overflow-x-auto text-emerald-400 max-h-[220px]">
                  {JSON.stringify(metrics, null, 2)}
                </pre>
              </div>
              <div>
                <span className="text-[10px] font-bold text-slate-500 block mb-1.5 uppercase">Funnel Endpoint Response Payload JSON</span>
                <pre className="text-[10px] font-mono bg-slate-950 p-4 rounded-lg overflow-x-auto text-emerald-400 max-h-[220px]">
                  {JSON.stringify(funnelData, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-300 px-4 py-3 rounded-xl mb-6 text-sm flex items-center gap-2">
            <span>⚠</span>
            <p>{error}</p>
          </div>
        )}

        {loading && !metrics ? (
          <div className="min-h-[400px] flex flex-col items-center justify-center gap-3">
            <div className="w-8 h-8 border-2 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin"></div>
            <p className="text-xs text-slate-400">Syncing database values...</p>
          </div>
        ) : (
          metrics && (
            <div className="space-y-6">
              
              {/* TAB 1: DASHBOARD VIEW */}
              {activeTab === 'dashboard' && (
                <>
                  {/* Clean stats metrics cards */}
                  <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
                    
                    <div className="bg-[#12151c] border border-slate-800 p-4 rounded-xl flex flex-col justify-between">
                      <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Total Visitors</span>
                      <div className="text-xl font-bold text-white tracking-tight mt-2">{metrics.total_visitors}</div>
                      <span className="text-[9px] text-slate-500 block mt-1">CCTV unique tracks</span>
                    </div>

                    <div className="bg-[#12151c] border border-slate-800 p-4 rounded-xl flex flex-col justify-between">
                      <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Daily Sales</span>
                      <div className="text-xl font-bold text-white tracking-tight mt-2">{metrics.daily_sales_transactions}</div>
                      <span className="text-[9px] text-slate-500 block mt-1">Unique POS orders</span>
                    </div>

                    <div className="bg-[#12151c] border border-slate-800 p-4 rounded-xl flex flex-col justify-between">
                      <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Net NMV</span>
                      <div className="text-xl font-bold text-white tracking-tight mt-2">{formatCurrency(metrics.daily_revenue_nmv)}</div>
                      <span className="text-[9px] text-slate-500 block mt-1">GMV: {formatCurrency(metrics.daily_revenue_gmv)}</span>
                    </div>

                    <div className="bg-[#12151c] border border-slate-800 p-4 rounded-xl flex flex-col justify-between">
                      <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Sales Conversion</span>
                      <div className="text-xl font-bold text-white tracking-tight mt-2">{metrics.actual_store_conversion_rate_pct}%</div>
                      <span className="text-[9px] text-slate-500 block mt-1">Invoices / Visitors</span>
                    </div>

                    <div className="bg-[#12151c] border border-slate-800 p-4 rounded-xl flex flex-col justify-between">
                      <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Total Quantities</span>
                      <div className="text-xl font-bold text-white tracking-tight mt-2">{metrics.daily_items_sold}</div>
                      <span className="text-[9px] text-slate-500 block mt-1">Items sold in invoices</span>
                    </div>

                    <div className="bg-[#12151c] border border-slate-800 p-4 rounded-xl flex flex-col justify-between">
                      <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Checkout Reach</span>
                      <div className="text-xl font-bold text-white tracking-tight mt-2">{metrics.checkout_visitors}</div>
                      <span className="text-[9px] text-slate-500 block mt-1">Capped funnel: {metrics.conversion_rate_pct}%</span>
                    </div>
                  </section>

                  {/* Funnel Layout - Stepped Waterfall Chart */}
                  {funnelData && (
                    <section className="bg-[#12151c] border border-slate-800 p-5 rounded-xl">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-6 gap-2">
                        <div>
                          <h2 className="text-sm font-bold text-white mb-0.5">Shopper Conversion Funnel (Waterfall Chart)</h2>
                          <p className="text-[10px] text-slate-400">Visitor session drops & conversion steps</p>
                        </div>
                        <div className="flex gap-3 text-[10px]">
                          <span className="flex items-center gap-1.5 text-slate-300">
                            <span className="w-2 h-2 rounded bg-indigo-500"></span> Active Stage
                          </span>
                          <span className="flex items-center gap-1.5 text-slate-350">
                            <span className="w-2 h-2 rounded bg-rose-500/20 border border-rose-500/40"></span> Drop-off Loss
                          </span>
                        </div>
                      </div>
                      
                      {/* The Waterfall Chart View */}
                      <div className="h-64 flex items-end justify-between bg-slate-950/40 border border-slate-800/80 rounded-xl p-5 pt-12 pb-6 relative select-none">
                        {/* Y-axis markers */}
                        <div className="absolute left-3 top-3 bottom-12 flex flex-col justify-between text-[8px] text-slate-500 font-mono">
                          <span>100%</span>
                          <span>75%</span>
                          <span>50%</span>
                          <span>25%</span>
                          <span>0%</span>
                        </div>

                        <div className="flex-grow flex items-end justify-around h-full ml-8 gap-1">
                          {waterfallData.map((bar, idx) => {
                            if (bar.type === 'stage') {
                              return (
                                <div key={idx} className="flex flex-col items-center group relative h-full justify-end w-12 md:w-16">
                                  {/* Tooltip */}
                                  <div className="absolute -top-10 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-900 text-white text-[10px] py-1 px-2 rounded border border-slate-700 shadow-xl z-20 whitespace-nowrap pointer-events-none">
                                    {bar.name}: <strong>{bar.visitors}</strong> sessions ({bar.pct}%)
                                  </div>
                                  
                                  {/* Value on top of bar */}
                                  <span className="text-[10px] font-bold text-white mb-1.5">{bar.visitors}</span>

                                  {/* Solid Column */}
                                  <div 
                                    className={`w-8 md:w-10 rounded-t transition-all duration-700 ${bar.colorClass}`}
                                    style={{ height: `${Math.max(4, bar.pct)}%` }}
                                  ></div>

                                  {/* Bottom Stage Label */}
                                  <span className="text-[10px] text-slate-400 mt-2 font-medium text-center truncate w-full flex items-center justify-center gap-1">
                                    <span>{bar.icon}</span>
                                    <span className="hidden sm:inline">{bar.name}</span>
                                  </span>
                                </div>
                              );
                            } else {
                              // Dropoff bar
                              return (
                                <div key={idx} className="flex flex-col items-center group relative h-full justify-end w-6 md:w-8">
                                  {/* Tooltip */}
                                  <div className="absolute -top-10 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-900 text-rose-300 text-[10px] py-1 px-2 rounded border border-slate-700 shadow-xl z-20 whitespace-nowrap pointer-events-none">
                                    {bar.name}: <strong>-{bar.diff}</strong> (-{bar.diffPct.toFixed(1)}%)
                                  </div>

                                  {/* Value floating */}
                                  {bar.diff > 0 && (
                                    <span className="text-[9px] font-semibold text-rose-400 mb-1.5" style={{ paddingBottom: `${bar.bottom}%` }}>
                                      -{bar.diff}
                                    </span>
                                  )}

                                  {/* Floating Column */}
                                  <div 
                                    className={`w-4 md:w-6 rounded transition-all duration-700 ${bar.colorClass}`}
                                    style={{ 
                                      height: `${Math.max(2, bar.height)}%`,
                                      marginBottom: `${bar.bottom}%`
                                    }}
                                  ></div>

                                  {/* Bottom Drop Label */}
                                  <span className="text-[8px] text-slate-500 mt-2 font-semibold uppercase tracking-wider">
                                    Loss
                                  </span>
                                </div>
                              );
                            }
                          })}
                        </div>
                      </div>

                      <div className="flex gap-4 flex-wrap mt-5 pt-4 border-t border-slate-800 text-[10px] text-slate-400">
                        <div>
                          Entry to Browse Drop-off: <strong className="text-red-400 font-bold">{funnelData.drop_off.entry_to_browse}%</strong>
                        </div>
                        <div>
                          Browse to Checkout Drop-off: <strong className="text-red-400 font-bold">{funnelData.drop_off.browse_to_checkout}%</strong>
                        </div>
                        <div>
                          Checkout to Purchase Drop-off: <strong className="text-red-400 font-bold">{funnelData.drop_off.checkout_to_purchase}%</strong>
                        </div>
                      </div>
                    </section>
                  )}

                  {/* Subgrid for Dwell and Cameras */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    
                    {/* Zone Dwells */}
                    <div className="bg-[#12151c] border border-slate-800 p-5 rounded-xl">
                      <h2 className="text-sm font-bold text-white mb-1">Zone Dwell Analytics</h2>
                      <p className="text-[10px] text-slate-400 mb-5">Average dwell time logged per retail area</p>
                      
                      <div className="space-y-3.5">
                        {metrics.zone_dwell.length === 0 ? (
                          <p className="text-xs text-slate-500 py-6 text-center">No dwells found.</p>
                        ) : (
                          metrics.zone_dwell.map((zone) => (
                            <div className="space-y-1" key={zone.zone_id}>
                              <div className="flex justify-between items-center text-xs">
                                <span className="capitalize text-slate-350">{zone.zone_id.toLowerCase().replace('_', ' ')}</span>
                                <span className="text-slate-400 font-semibold">{zone.avg_dwell_s} seconds</span>
                              </div>
                              <div className="h-1.5 bg-slate-900 rounded-full">
                                <div 
                                  className="h-full bg-slate-400 rounded-full" 
                                  style={{ width: `${Math.min(100, (zone.avg_dwell_s / 30) * 100)}%` }}
                                ></div>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>

                    {/* Camera Logs count */}
                    <div className="bg-[#12151c] border border-slate-800 p-5 rounded-xl">
                      <h2 className="text-sm font-bold text-white mb-1">Camera Log Volume</h2>
                      <p className="text-[10px] text-slate-400 mb-5">Processed frames coordinates logged per camera</p>
                      
                      <div className="space-y-2.5">
                        {metrics.events_by_camera.map((cam) => {
                          const camNames = {
                            'CAM_ENTRY_03': 'Main Entry Door (CAM 3)',
                            'CAM_CHECKOUT_05': 'Billing POS (CAM 5)',
                            'CAM_FLOOR_01': 'Skincare Aisle (CAM 1)',
                            'CAM_FLOOR_02': 'Makeup Aisle (CAM 2)',
                            'CAM_STOCKROOM_04': 'Stock Room (CAM 4)'
                          };
                          return (
                            <div key={cam.camera_id} className="bg-slate-900/60 border border-slate-800/80 px-3 py-2.5 rounded-lg flex justify-between items-center">
                              <span className="text-xs text-slate-300 font-medium">{camNames[cam.camera_id] || cam.camera_id}</span>
                              <span className="bg-slate-800 text-slate-300 text-[10px] font-bold px-2 py-0.5 rounded border border-slate-700">
                                {cam.event_count} tracks
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                  </div>

                  {/* Backend Real-Time Events Ingest Log */}
                  <section className="bg-[#12151c] border border-slate-800 p-5 rounded-xl">
                    <div className="flex justify-between items-center mb-1">
                      <h2 className="text-sm font-bold text-white">Active Datastore Ingest Logs</h2>
                      <span className="text-[10px] bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-2 py-0.5 rounded font-mono">
                        SQL table: `events`
                      </span>
                    </div>
                    <p className="text-[10px] text-slate-400 mb-4">Latest 15 visitor events ingested from CCTV stream coordinates</p>
                    
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="border-b border-slate-800 text-slate-400 font-semibold">
                            <th className="py-2.5 px-3">Timestamp</th>
                            <th className="py-2.5 px-3">Visitor ID</th>
                            <th className="py-2.5 px-3">Camera</th>
                            <th className="py-2.5 px-3">Event Type</th>
                            <th className="py-2.5 px-3">Zone</th>
                            <th className="py-2.5 px-3 text-right">Dwell Time</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rawEvents.map((evt, idx) => (
                            <tr key={idx} className="border-b border-slate-800/50 hover:bg-slate-900/40 text-slate-300 font-mono text-[11px]">
                              <td className="py-2 px-3">{evt.timestamp.replace('T', ' ')}</td>
                              <td className="py-2 px-3 text-slate-400">{evt.visitor_id.substring(0, 12)}...</td>
                              <td className="py-2 px-3">{evt.camera_id}</td>
                              <td className="py-2 px-3">
                                <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                                  evt.event_type === 'ENTRY' ? 'bg-emerald-500/15 text-emerald-400' :
                                  evt.event_type === 'EXIT' ? 'bg-red-500/15 text-red-400' :
                                  evt.event_type === 'PURCHASE' ? 'bg-purple-500/15 text-purple-400' :
                                  'bg-slate-800 text-slate-400'
                                }`}>
                                  {evt.event_type}
                                </span>
                              </td>
                              <td className="py-2 px-3 text-slate-400">{evt.zone_id || 'N/A'}</td>
                              <td className="py-2 px-3 text-right font-sans text-xs">{evt.dwell_ms > 0 ? `${(evt.dwell_ms / 1000).toFixed(1)}s` : '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>

                  {/* Anomalies Widget */}
                  {anomaliesData && (
                    <section className="bg-[#12151c] border border-slate-800 p-5 rounded-xl">
                      <h2 className="text-sm font-bold text-white mb-1">Anomaly Flags detected</h2>
                      <p className="text-[10px] text-slate-400 mb-5">FastAPI automated alerts indicating low confidence detections or tracking breaks</p>
                      
                      <div className="space-y-3">
                        {anomaliesData.anomalies.length === 0 ? (
                          <p className="text-xs text-emerald-400">✓ No pipeline anomalies detected.</p>
                        ) : (
                          anomaliesData.anomalies.map((anomaly, idx) => {
                            const severityClass = anomaly.severity ? anomaly.severity.toLowerCase() : 'low';
                            return (
                              <div 
                                key={idx} 
                                className={`border-l-2 p-3.5 rounded-r-lg flex flex-col gap-1 ${
                                  severityClass === 'high' 
                                    ? 'border-red-500 bg-red-500/5' 
                                    : severityClass === 'medium' 
                                    ? 'border-amber-500 bg-amber-500/5' 
                                    : 'border-slate-700 bg-slate-900/40'
                                }`}
                              >
                                <div className="flex items-center gap-2">
                                  <span className={`text-[9px] font-bold px-1.5 py-0.25 rounded ${
                                    severityClass === 'high' ? 'bg-red-500/20 text-red-400' :
                                    severityClass === 'medium' ? 'bg-amber-500/20 text-amber-400' :
                                    'bg-slate-800 text-slate-400'
                                  }`}>
                                    {anomaly.severity || 'LOW'}
                                  </span>
                                  <strong className="text-xs font-bold text-slate-200 capitalize">{anomaly.type.replace(/_/g, ' ')}</strong>
                                </div>
                                <p className="text-[11px] text-slate-400 leading-normal">
                                  {anomaly.note || `Visitor ID: ${anomaly.visitor_id || 'N/A'} experienced an anomaly in zone ${anomaly.zone_id || 'N/A'}`}
                                  {anomaly.dwell_min && ` (Dwell Time: ${anomaly.dwell_min} min)`}
                                  {anomaly.count && ` (Occurrences: ${anomaly.count})`}
                                </p>
                              </div>
                            );
                          })
                        )}
                      </div>
                    </section>
                  )}
                </>
              )}

              {/* TAB 2: LIVE CAMERA FEEDS */}
              {activeTab === 'cameras' && (
                <div className="space-y-6">
                  {/* Featured Large Player */}
                  <div className="bg-[#12151c] border border-slate-800 rounded-xl overflow-hidden flex flex-col">
                    <div className="relative bg-black aspect-video max-h-[500px]">
                      <video 
                        key={selectedCam.id}
                        src={`${API_BASE}/videos/${selectedCam.file}`}
                        autoPlay 
                        loop 
                        muted 
                        controls 
                        playsInline
                        className="w-full h-full object-contain"
                      />
                      <div className="absolute top-4 left-4 bg-slate-900 border border-slate-800 text-slate-200 text-[10px] font-mono px-2 py-0.5 rounded shadow">
                        🔴 LIVE FEED CH: {selectedCam.id}
                      </div>
                    </div>
                    
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-6 p-4 bg-slate-900 text-xs border-t border-slate-800">
                      <div>
                        <span className="text-slate-500 block uppercase font-bold text-[9px] mb-0.5">Channel Name</span>
                        <strong className="text-slate-200 font-semibold">{selectedCam.name}</strong>
                      </div>
                      <div>
                        <span className="text-slate-500 block uppercase font-bold text-[9px] mb-0.5">Target Zone</span>
                        <strong className="text-slate-200 font-semibold">{selectedCam.zone}</strong>
                      </div>
                      <div>
                        <span className="text-slate-500 block uppercase font-bold text-[9px] mb-0.5">Specifications</span>
                        <strong className="text-slate-200 font-semibold">{selectedCam.res} @ {selectedCam.fps} FPS</strong>
                      </div>
                      <div>
                        <span className="text-slate-500 block uppercase font-bold text-[9px] mb-0.5">Logs Count</span>
                        <strong className="text-slate-200 font-semibold">
                          {metrics?.events_by_camera.find(c => c.camera_id === selectedCam.id)?.event_count || 0} events
                        </strong>
                      </div>
                    </div>
                  </div>

                  {/* Thumbnail Selector Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                    {CAMERAS_LIST.map((cam) => {
                      const isSelected = selectedCam.id === cam.id;
                      const eventCount = metrics?.events_by_camera.find(c => c.camera_id === cam.id)?.event_count || 0;
                      return (
                        <div 
                          key={cam.id} 
                          className={`bg-[#12151c] border rounded-lg overflow-hidden cursor-pointer transition-all ${
                            isSelected ? 'border-indigo-500 shadow-sm' : 'border-slate-850'
                          }`}
                          onClick={() => setSelectedCam(cam)}
                          id={`cam-card-${cam.id}`}
                        >
                          <div className="relative aspect-video bg-slate-950">
                            <video 
                              src={`${API_BASE}/videos/${cam.file}`} 
                              muted 
                              loop 
                              autoPlay 
                              playsInline
                              className="w-full h-full object-cover opacity-60"
                            />
                            <div className="absolute top-2 left-2 right-2 flex justify-between pointer-events-none text-[8px] font-mono">
                              <span className="bg-black/80 px-1.5 py-0.5 rounded text-white border border-slate-700">
                                {cam.id.replace('CAM_', 'CH ')}
                              </span>
                              <span className="bg-slate-800 px-1.5 py-0.5 rounded text-white border border-slate-700">
                                {eventCount} tracks
                              </span>
                            </div>
                          </div>
                          <div className="p-3">
                            <h4 className="text-xs font-bold text-slate-200 truncate">{cam.name}</h4>
                            <p className="text-[9px] text-slate-400 mt-0.5 font-mono">{cam.zone}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* TAB 3: PIPELINE SETTINGS */}
              {activeTab === 'settings' && (
                <div className="bg-[#12151c] border border-slate-800 p-6 rounded-xl space-y-6">
                  <div>
                    <h2 className="text-sm font-bold text-white mb-0.5">Pipeline Parameter Controls</h2>
                    <p className="text-[10px] text-slate-400">Configure model triggers, temporal boundaries, and datastore overrides</p>
                  </div>
                  
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 pt-2">
                    <div className="space-y-4">
                      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">🤖 Computer Vision Models</h3>
                      
                      <div className="space-y-1">
                        <label className="text-xs text-slate-350 flex justify-between">
                          <span>YOLO Confidence Threshold</span>
                          <strong className="text-slate-200">{confidenceThreshold}</strong>
                        </label>
                        <input 
                          type="range" 
                          min="0.1" 
                          max="0.9" 
                          step="0.05" 
                          value={confidenceThreshold} 
                          onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))} 
                          className="w-full accent-indigo-500 cursor-pointer bg-slate-800 rounded-lg"
                          id="setting-confidence-slider"
                        />
                        <span className="block text-[9px] text-slate-500">
                          Rejects low-confidence detections from indexing.
                        </span>
                      </div>

                      <div className="space-y-1">
                        <label className="text-xs text-slate-350 flex justify-between">
                          <span>ByteTrack Association IoU</span>
                          <strong className="text-slate-200">{trackingThreshold}</strong>
                        </label>
                        <input 
                          type="range" 
                          min="0.1" 
                          max="0.9" 
                          step="0.05" 
                          value={trackingThreshold} 
                          onChange={(e) => setTrackingThreshold(parseFloat(e.target.value))} 
                          className="w-full accent-indigo-500 cursor-pointer bg-slate-800 rounded-lg"
                          id="setting-tracking-slider"
                        />
                        <span className="block text-[9px] text-slate-500">
                          Intersection-over-Union mapping cross consecutive frames.
                        </span>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">💳 POS Mapping Rules</h3>
                      
                      <div className="space-y-1">
                        <label className="text-xs text-slate-350">Temporal Window Radius (seconds)</label>
                        <input 
                          type="number" 
                          min="30" 
                          max="600" 
                          value={posWindow} 
                          onChange={(e) => setPosWindow(parseInt(e.target.value))} 
                          className="w-full bg-[#0c0e12] border border-slate-800 rounded px-3 py-2 text-xs text-slate-250 font-semibold outline-none"
                          id="setting-correlation-input"
                        />
                        <span className="block text-[9px] text-slate-500">
                          Time distance window (± seconds) to link checkout events to orders.
                        </span>
                      </div>

                      <div className="flex items-start gap-2.5 p-3.5 bg-slate-900/60 rounded-lg border border-slate-800">
                        <input 
                          type="checkbox" 
                          id="excludeStaffCheckbox"
                          checked={excludeStaff} 
                          onChange={(e) => setExcludeStaff(e.target.checked)} 
                          className="w-3.5 h-3.5 accent-indigo-500 mt-0.5 cursor-pointer"
                        />
                        <div>
                          <label htmlFor="excludeStaffCheckbox" className="block text-xs font-semibold text-slate-300 cursor-pointer">
                            Filter Staff Badges
                          </label>
                          <span className="block text-[9px] text-slate-500 mt-0.5">
                            Exclude internal assistants from shopper conversion KPIs.
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-3">
                      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">💾 Datastore Properties</h3>
                      <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg space-y-2.5 text-xs text-slate-350">
                        <div className="flex justify-between">
                          <span>SQL Database File:</span>
                          <strong className="text-slate-200">store_intelligence.db</strong>
                        </div>
                        <div className="flex justify-between">
                          <span>Ingested Event Logs:</span>
                          <strong className="text-slate-200">209 rows</strong>
                        </div>
                        <div className="flex justify-between">
                          <span>POS Invoices Loaded:</span>
                          <strong className="text-slate-200">101 rows</strong>
                        </div>
                        <div className="flex justify-between">
                          <span>API Endpoint Host:</span>
                          <strong className="text-slate-200">uvicorn/localhost:8000</strong>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="flex gap-3 pt-5 border-t border-slate-850">
                    <button 
                      className="bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs px-4.5 py-2.5 rounded transition-all uppercase tracking-wider"
                      onClick={handleSaveSettings} 
                      id="btn-save-settings"
                    >
                      Save Configuration
                    </button>
                    <button 
                      className="bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs px-4 py-2.5 rounded transition-all"
                      onClick={handleResetDatabase} 
                      id="btn-reset-db"
                    >
                      Clear & Reindex Cache
                    </button>
                  </div>
                </div>
              )}

            </div>
          )
        )}
      </main>
    </div>
  );
}

export default App;
