"use client"

import { Sparkles, Zap, BookOpen, Code2, Globe, Lightbulb } from "lucide-react"

const suggestions = [
  {
    icon: BookOpen,
    label: "Research & Summarize",
    prompt: "Explain how retrieval-augmented generation works and its key benefits",
  },
  {
    icon: Code2,
    label: "Technical Deep Dive",
    prompt: "Compare Pinecone, Weaviate, and pgvector for production RAG systems",
  },
  {
    icon: Lightbulb,
    label: "Concepts Explained",
    prompt: "What is the difference between fine-tuning and RAG for LLM customization?",
  },
  {
    icon: Globe,
    label: "Current Events",
    prompt: "What are the latest advances in AI language models in 2025?",
  },
]

interface WelcomeScreenProps {
  onSuggestionClick: (prompt: string) => void
}

export function WelcomeScreen({ onSuggestionClick }: WelcomeScreenProps) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 px-4 py-12 text-center">
      {/* Logo mark */}
      <div className="w-14 h-14 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-6">
        <Sparkles className="w-7 h-7 text-primary" />
      </div>

      <h1 className="text-2xl font-semibold text-foreground mb-2 text-balance">
        What would you like to know?
      </h1>
      <p className="text-sm text-muted-foreground mb-10 max-w-md text-balance leading-relaxed">
        Ask anything — get precise, cited answers drawn from trusted sources using
        retrieval-augmented generation.
      </p>

      {/* Suggestion grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-xl">
        {suggestions.map(({ icon: Icon, label, prompt }) => (
          <button
            key={label}
            onClick={() => onSuggestionClick(prompt)}
            className="group flex items-start gap-3 p-3.5 rounded-xl border border-border bg-card hover:bg-accent hover:border-primary/30 text-left transition-all duration-150"
          >
            <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center shrink-0 group-hover:bg-primary/10 transition-colors mt-0.5">
              <Icon className="w-4 h-4 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-foreground mb-0.5">{label}</p>
              <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">{prompt}</p>
            </div>
          </button>
        ))}
      </div>

      <div className="flex items-center gap-1.5 mt-10 text-xs text-muted-foreground/60">
        <Zap className="w-3.5 h-3.5" />
        <span>Powered by retrieval-augmented generation</span>
      </div>
    </div>
  )
}
