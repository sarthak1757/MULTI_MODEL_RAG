import { useEffect, useMemo, useState } from "react";
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
        <header className="hero">
          <h1>Multimodal Event RAG</h1>
          <p>Event-centric retrieval across transcript, video frames, OCR and evidence relationships.</p>
        </header>
        {error && <div className="errorBanner">{error}</div>}
        <ActiveSource source={activeSource} onChangeSource={() => setUploadOpen(false)} />
        <ProcessingProgress result={processResult} processing={processing} />
        <QuestionBox
          question={question}
          disabled={!activeSource || activeSource.status !== "ready" || loadingAnswer}
          loading={loadingAnswer}
          onChange={setQuestion}
          onAsk={handleAsk}
        />
        <AnswerPanel answer={answer} />
        {answer && (
          <section className="panel">
            <span className="eyebrow">Retrieved Evidence</span>
            <div className="evidenceGrid">
              {answer.evidence.map((event) => <EvidenceCard key={event.event_id} event={event} />)}
            </div>
          </section>
        )}
        <EventTimeline events={events} highlightedIds={highlightedIds} />
      </main>
      <SourceUploader open={uploadOpen} onClose={() => setUploadOpen(false)} onUploadAndProcess={uploadAndProcess} />
    </div>
  );
}
