interface Scheme {
  scheme_name: string;
  details: string;
  benefits: string;
  eligibility: string;
  application: string;
  documents: string;
  level: string;
  schemeCategory: string;
  tags: string;
  score: number;
}

interface Props {
  scheme: Scheme;
}

function InfoRow({ label, value }: { label: string; value: string }) {
  if (!value || value === "nan") return null;
  return (
    <div className="mt-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-1">
        {label}
      </p>
      <p className="text-sm text-gray-700 leading-relaxed">{value}</p>
    </div>
  );
}

export default function SchemeCard({ scheme }: Props) {
  const tags = scheme.tags
    ? scheme.tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean)
    : [];

  return (
    <article className="bg-white rounded-2xl shadow-md border border-gray-100 p-6 hover:shadow-lg transition-shadow">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <h2 className="text-lg font-bold text-gray-800 leading-snug">
          {scheme.scheme_name}
        </h2>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {scheme.level && scheme.level !== "nan" && (
            <span className="text-xs bg-blue-100 text-blue-700 font-medium px-2.5 py-0.5 rounded-full">
              {scheme.level}
            </span>
          )}
          {scheme.schemeCategory && scheme.schemeCategory !== "nan" && (
            <span className="text-xs bg-orange-100 text-orange-700 font-medium px-2.5 py-0.5 rounded-full">
              {scheme.schemeCategory}
            </span>
          )}
        </div>
      </div>

      {/* Body */}
      <InfoRow label="Details" value={scheme.details} />
      <InfoRow label="Benefits" value={scheme.benefits} />
      <InfoRow label="Eligibility" value={scheme.eligibility} />
      <InfoRow label="How to Apply" value={scheme.application} />
      <InfoRow label="Documents Required" value={scheme.documents} />

      {/* Tags */}
      {tags.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {tags.map((tag, i) => (
            <span
              key={i}
              className="text-xs bg-gray-100 text-gray-600 px-2.5 py-0.5 rounded-full"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}
