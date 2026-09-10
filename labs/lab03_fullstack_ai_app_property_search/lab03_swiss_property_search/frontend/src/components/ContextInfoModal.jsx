import React, { useState } from 'react';
import { Code, FileJson, Copy, Check, Database, X, Info } from 'lucide-react';

const DDL_DATA = {
    alloydb: `/* ALLOYDB PG SCHEMA & METADATA COMMENTS */
CREATE TABLE property_listings (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(12, 2) NOT NULL,
    bedrooms INT,
    city VARCHAR(100),
    image_gcs_uri TEXT,
    country VARCHAR(100) DEFAULT 'Switzerland',
    canton VARCHAR(100),
    description_embedding VECTOR(3072),
    image_embedding VECTOR(1408) 
);

-- COLUMN METADATA COMMENTS (Gemini Context Enrichment)
COMMENT ON COLUMN property_listings.bedrooms IS '<gemini>Examples: [''4'', ''6'', ''3''] | Distinct Values: 7 | Null Count: 0 |</gemini>';
COMMENT ON COLUMN property_listings.city IS '<gemini>Examples: [''Stans'', ''Altdorf'', ''Kilchberg''] | Distinct Values: 89 | Null Count: 0 |</gemini>';
COMMENT ON COLUMN property_listings.canton IS '<gemini>Examples: [''Solothurn'', ''Ticino'', ''Zug''] | Distinct Values: 27 | Null Count: 0 |</gemini>';
COMMENT ON COLUMN property_listings.price IS '<gemini>Examples: [''11878.00'', ''4869.00'', ''2792.00''] | Distinct Values: 189 | Null Count: 0 |</gemini>';`
};

export default function ContextInfoModal({ isOpen, onClose, activeBackend, contextData }) {
    const [activeTab, setActiveTab] = useState('ddl');
    const [copied, setCopied] = useState(false);

    if (!isOpen) return null;

    const ddlText = DDL_DATA[activeBackend] || '-- No schema DDL mapped';
    const jsonText = JSON.stringify(contextData, null, 2);

    const handleCopy = () => {
        const textToCopy = activeTab === 'ddl' ? ddlText : jsonText;
        navigator.clipboard.writeText(textToCopy);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const getBackendLabel = () => {
        switch (activeBackend) {
            case 'alloydb': return 'AlloyDB';
            case 'spanner': return 'Cloud Spanner';
            case 'cloudsql_pg': return 'Cloud SQL PostgreSQL';
            case 'cloudsql_mysql': return 'Cloud SQL MySQL';
            default: return activeBackend;
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in duration-200" onClick={onClose}>
            <div 
                className="bg-slate-900 border border-slate-850 rounded-2xl max-w-5xl w-full h-[85vh] flex flex-col shadow-2xl relative overflow-hidden animate-in zoom-in-95 duration-300"
                onClick={e => e.stopPropagation()}
            >
                {/* HEADER */}
                <div className="px-6 py-4 bg-slate-950 border-b border-slate-800 flex justify-between items-center">
                    <div className="flex items-center gap-2">
                        <Database className="w-5 h-5 text-indigo-400" />
                        <span className="font-bold text-white text-lg">
                            {getBackendLabel()} Context Configuration
                        </span>
                    </div>
                    <div className="flex items-center gap-3">
                        <button 
                            onClick={handleCopy} 
                            className="px-3 py-1.5 text-xs rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-white transition-all flex items-center gap-1.5 font-medium"
                            title="Copy Active Panel Content"
                        >
                            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                            {copied ? 'Copied!' : 'Copy Code'}
                        </button>
                        <button 
                            onClick={onClose} 
                            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
                            aria-label="Close context info modal"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                {/* SUBHEADER INFO */}
                <div className="bg-slate-950/40 border-b border-slate-850/50 px-6 py-3 text-xs text-slate-400 flex items-center gap-2">
                    <Info className="w-4 h-4 text-indigo-400 flex-shrink-0" />
                    <span>
                        This panel showcases how <strong>{getBackendLabel()}</strong> enriches query translations. GDA parses table column comments to understand content limits, while templates/value-searches are read from `contextSet.json`.
                    </span>
                </div>

                {/* TABS */}
                <div className="px-6 bg-slate-950 border-b border-slate-850 flex gap-2">
                    <button
                        onClick={() => setActiveTab('ddl')}
                        className={`py-3 px-4 border-b-2 text-xs font-bold uppercase tracking-wider flex items-center gap-2 transition-all ${
                            activeTab === 'ddl' 
                                ? 'border-indigo-500 text-indigo-400' 
                                : 'border-transparent text-slate-400 hover:text-slate-200'
                        }`}
                    >
                        <Code className="w-4 h-4" /> Table DDL & Schema Comments
                    </button>
                    <button
                        onClick={() => setActiveTab('json')}
                        className={`py-3 px-4 border-b-2 text-xs font-bold uppercase tracking-wider flex items-center gap-2 transition-all ${
                            activeTab === 'json' 
                                ? 'border-indigo-500 text-indigo-400' 
                                : 'border-transparent text-slate-400 hover:text-slate-200'
                        }`}
                    >
                        <FileJson className="w-4 h-4" /> contextSet.json File
                    </button>
                </div>

                {/* CONTENT PANEL */}
                <div className="flex-1 overflow-auto p-6 bg-slate-950 custom-scrollbar">
                    {activeTab === 'ddl' ? (
                        <pre className="font-mono text-xs text-slate-300 leading-relaxed whitespace-pre overflow-x-auto select-text">
                            {ddlText}
                        </pre>
                    ) : (
                        <pre className="font-mono text-xs text-indigo-300 leading-relaxed whitespace-pre overflow-x-auto select-text">
                            {jsonText}
                        </pre>
                    )}
                </div>
            </div>
        </div>
    );
}
