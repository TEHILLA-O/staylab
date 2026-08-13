export function LoadingState() {
  return (
    <main className="mx-auto max-w-[880px] px-6 py-16 sm:px-10">
      <p className="font-serif text-3xl text-ink">StayLab</p>
      <div className="mt-16 space-y-6">
        <div className="h-3 w-40 bg-line" />
        <div className="h-10 w-72 bg-line" />
        <div className="mt-12 grid grid-cols-2 gap-10">
          <div className="h-24 bg-line/70" />
          <div className="h-24 bg-line/70" />
        </div>
        <p className="pt-8 text-sm text-mute">Reading the experiment from PostgreSQL…</p>
      </div>
    </main>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <main className="mx-auto max-w-[720px] px-6 py-24 sm:px-10">
      <p className="font-serif text-3xl text-ink">StayLab</p>
      <h1 className="mt-16 font-serif text-4xl leading-tight text-ink">
        Analytics unavailable
      </h1>
      <p className="mt-6 max-w-md text-[17px] leading-relaxed text-mute">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-10 border border-ink px-4 py-2 text-sm text-ink hover:bg-ink hover:text-canvas"
      >
        Try again
      </button>
    </main>
  );
}

export function EmptyState() {
  return (
    <main className="mx-auto max-w-[720px] px-6 py-24 sm:px-10">
      <p className="font-serif text-3xl text-ink">StayLab</p>
      <h1 className="mt-16 font-serif text-4xl leading-tight text-ink">No experiment loaded</h1>
      <p className="mt-6 max-w-md text-[17px] leading-relaxed text-mute">
        The API is up, but PostgreSQL has no experiment rows yet. Run the pipeline, then reload.
      </p>
      <pre className="mt-8 overflow-x-auto border border-line bg-surface p-4 font-mono text-xs text-mute">
        docker compose up -d db{"\n"}
        python -m analytics.pipeline --readout
      </pre>
    </main>
  );
}
