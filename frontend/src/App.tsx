import { useEffect, useMemo, useState } from "react";
import { Plus, Radio } from "lucide-react";
import { askQuestion, deleteSource, getEvents, getSource, getSources, processSource, uploadSource } from "./api/client";
import ActiveSource from "./components/ActiveSource";
import AnswerPanel from "./components/AnswerPanel";
import EventTimeline from "./components/EventTimeline";
import EvidenceCard from "./components/EvidenceCard";
import ProcessingProgress from "./components/ProcessingProgress";
import QuestionBox from "./components/QuestionBox";
import SourceSidebar from "./components/SourceSidebar";
import SourceUploader from "./components/SourceUploader";
import type { ProcessResult, QueryResponse, Source, TimelineEvent } from "./types/api";

const DEFAULT_QUESTION = "Why is English useful for solving global problems?";

export default function App() {
  const [sources, setSources] = useState<Source[]>([]);
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null);
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [answer, setAnswer] = useState<QueryResponse | null>(null);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [processResult, setProcessResult] = useState<ProcessResult | null>(null);
  const [loadingAnswer, setLoadingAnswer] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeSource = useMemo(
    () => sources.find((source) => source.id === activeSourceId) ?? sources.find((source) => source.status === "ready") ?? sources[0] ?? null,
    [sources, activeSourceId]
  );

  const sourceStats = useMemo(() => ({
    total: sources.length,
    ready: sources.filter((source) => source.status === "ready").length,
    processing: sources.filter((source) => source.status === "processing").length,
    failed: sources.filter((source) => source.status === "failed").length
  }), [sources]);

  async function refreshSources(selectId?: string): Promise<Source[]> {
    const nextSources = await getSources();
    setSources(nextSources);
    setError(null);
    if (selectId) {
      const selected = nextSources.find((source) => source.id === selectId);
      if (selected?.status === "ready") {
        setActiveSourceId(selectId);
      }
      return nextSources;
    }
    if (!activeSourceId && nextSources.length) {
      setActiveSourceId((nextSources.find((source) => source.status === "ready") ?? nextSources[0]).id);
    }
    return nextSources;
  }

  useEffect(() => {
    refreshSources().catch(() => setError("API unavailable. Start the FastAPI backend on port 8000."));
  }, []);

  useEffect(() => {
    setError(null);
    setAnswer(null);
  }, [activeSourceId]);

  useEffect(() => {
    if (!activeSource || activeSource.status !== "ready") {
      setEvents([]);
      return;
    }
    getEvents(activeSource.id)
      .then((nextEvents) => {
        setEvents(nextEvents);
        setError(null);
      })
      .catch((err) => {
        setEvents([]);
        setError(err instanceof Error ? err.message : "Event endpoint unavailable.");
      });
  }, [activeSource?.id, activeSource?.status]);

  async function selectSource(source: Source) {
    setError(null);
    setAnswer(null);
    try {
      const exactSource = await getSource(source.id);
      setError(null);
      setActiveSourceId(exactSource.id);
      if (exactSource.status === "ready") {
        getEvents(exactSource.id)
          .then((nextEvents) => {
            setEvents(nextEvents);
            setError(null);
          })
          .catch((err) => {
            setEvents([]);
            setError(err instanceof Error ? err.message : "Event endpoint unavailable.");
          });
      } else {
        setEvents([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Source selection failed.");
    }
  }

  async function uploadAndProcess(file: File): Promise<ProcessResult> {
    setProcessing(true);
    setProcessResult(null);
    let uploadedId: string | null = null;
    try {
      const uploaded = await uploadSource(file);
      uploadedId = uploaded.source_id ?? uploaded.id;
      const processed = await processSource(uploadedId);
      setProcessResult(processed);
      const refreshed = await refreshSources();
      const processedSource = refreshed.find((source) => source.id === uploadedId);
      if (processed.status === "ready" && processedSource?.status === "ready") {
        setActiveSourceId(uploadedId);
        setAnswer(null);
        setQuestion(DEFAULT_QUESTION);
        setUploadOpen(false);
      } else {
        throw new Error(processed.error ?? processedSource?.error_message ?? "Processing failed.");
      }
      return processed;
    } catch (err) {
      if (uploadedId) {
        await refreshSources().catch(() => undefined);
      }
      throw err;
    } finally {
      setProcessing(false);
    }
  }

  async function retrySource(source: Source) {
    setError(null);
    const processed = await processSource(source.id);
    await refreshSources();
    if (processed.status !== "ready") {
      throw new Error(processed.error ?? "Processing failed.");
    }
  }

  async function removeSource(source: Source) {
    setError(null);
    await deleteSource(source.id);
    const refreshed = await refreshSources();
    if (activeSourceId === source.id) {
      setActiveSourceId(refreshed.find((candidate) => candidate.status === "ready")?.id ?? null);
    }
  }

  async function handleAsk() {
    if (!activeSource || activeSource.status !== "ready") return;
    setLoadingAnswer(true);
    setError(null);
    try {
      const nextAnswer = await askQuestion(activeSource.id, question);
      setAnswer(nextAnswer);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Question failed.");
    } finally {
      setLoadingAnswer(false);
    }
  }

  const highlightedIds = new Set(answer?.evidence.map((event) => event.event_id) ?? []);
  const sourceHealth = sourceStats.total ? Math.round((sourceStats.ready / sourceStats.total) * 100) : 0;

  return (
    <div className="appShell">
      <SourceSidebar
        sources={sources}
        activeSourceId={activeSource?.id ?? null}
        onSelect={selectSource}
        onAdd={() => setUploadOpen(true)}
        onRetry={retrySource}
        onDelete={removeSource}
      />
      <main className="mainContent">
        <header className="topBar">
          <div className="workspaceIdentity">
            <span className="brandMark" aria-hidden="true"><Radio size={18} strokeWidth={2.2} /></span>
            <div>
              <span className="eyebrow">Multimodal retrieval</span>
              <h1>Research Console</h1>
            </div>
          </div>
          <div className="topBarActions">
            <span className="connectionStatus"><i /> System online</span>
            <button className="primaryButton iconTextButton" onClick={() => setUploadOpen(true)}><Plus size={16} />Add source</button>
          </div>
        </header>
        {error && <div className="errorBanner">{error}</div>}
        <section className="workspaceIntro">
          <div>
            <span className="eyebrow">Evidence-first analysis</span>
            <h2>Ask across every moment in your source.</h2>
            <p>Trace answers back to speech, OCR, frames, PDFs, and image observations without leaving the workspace.</p>
          </div>
          <div className="healthMeter" aria-label={`${sourceHealth}% of sources ready`}>
            <div className="healthMeterHeader"><span>Library readiness</span><strong>{sourceHealth}%</strong></div>
            <div className="meterTrack"><span style={{ width: `${sourceHealth}%` }} /></div>
            <small>{sourceStats.ready} of {sourceStats.total} sources ready to query</small>
          </div>
        </section>
        <section className="overviewGrid" aria-label="Workspace status">
          <div><strong>{sourceStats.total}</strong><span>Sources</span></div>
          <div><strong>{sourceStats.ready}</strong><span>Ready</span></div>
          <div><strong>{events.length}</strong><span>Timeline events</span></div>
          <div><strong>{answer?.evidence.length ?? 0}</strong><span>Evidence hits</span></div>
        </section>
        <div className="workspaceGrid">
          <section className="analysisColumn">
            <QuestionBox
              question={question}
              disabled={!activeSource || activeSource.status !== "ready" || loadingAnswer}
              loading={loadingAnswer}
              onChange={setQuestion}
              onAsk={handleAsk}
            />
            <AnswerPanel answer={answer} />
            {answer && (
              <section className="panel evidencePanel">
                <div className="sectionHeader">
                  <div><span className="eyebrow">Retrieved evidence</span><h2>Evidence ledger</h2></div>
                  <span className="sectionMeta">{answer.evidence.length} ranked moments</span>
                </div>
                <div className="evidenceGrid">
                  {answer.evidence.map((event) => <EvidenceCard key={event.event_id} event={event} />)}
                </div>
              </section>
            )}
            <EventTimeline events={events} highlightedIds={highlightedIds} />
          </section>
          <aside className="contextRail">
            <ActiveSource source={activeSource} onChangeSource={() => setUploadOpen(true)} />
            <ProcessingProgress result={processResult} processing={processing} />
            <section className="panel systemPanel">
              <span className="eyebrow">Workspace signal</span>
              <h2>Index overview</h2>
              <dl>
                <div><dt>Ready sources</dt><dd>{sourceStats.ready}</dd></div>
                <div><dt>In processing</dt><dd>{sourceStats.processing}</dd></div>
                <div><dt>Needs attention</dt><dd>{sourceStats.failed}</dd></div>
              </dl>
              <p className="muted">Every query is grounded in the source evidence stored in your local index.</p>
            </section>
          </aside>
        </div>
      </main>
      <SourceUploader open={uploadOpen} onClose={() => setUploadOpen(false)} onUploadAndProcess={uploadAndProcess} />
    </div>
  );
}
