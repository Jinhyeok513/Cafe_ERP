export default function Loading() {
  return (
    <div className="loading-shell" aria-label="Loading operations dashboard">
      <div className="loading-sidebar" />
      <main className="loading-content">
        <div className="skeleton line wide" />
        <div className="skeleton-grid">
          {Array.from({ length: 4 }).map((_, index) => <div className="skeleton block" key={index} />)}
        </div>
        <div className="skeleton panel" />
      </main>
    </div>
  );
}
