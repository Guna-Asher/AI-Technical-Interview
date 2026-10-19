import StartInterviewForm from "@/components/StartInterviewForm";

const STEPS = [
  "Enter the role you are preparing for.",
  "Upload your resume as a PDF or text file.",
  "Answer the questions, then read your feedback.",
];

export default function Home() {
  return (
    <div className="mx-auto grid w-full max-w-5xl grid-cols-1 gap-10 px-4 py-10 sm:px-6 sm:py-14 lg:grid-cols-[minmax(0,1fr)_26rem] lg:gap-16 lg:py-20">
      <section aria-labelledby="intro-title" className="min-w-0">
        <h1 id="intro-title" className="text-4xl font-semibold tracking-tight sm:text-5xl sm:leading-[1.1]">
          Practise the interview you are about to have.
        </h1>
        <p className="mt-5 max-w-prose text-lg text-graphite">
          Questions are written from your resume and grounded in technical reference passages. Every answer gets written
          feedback, and you finish with a saved report.
        </p>
        <ol className="mt-8 flex flex-col gap-3">
          {STEPS.map((step, index) => (
            <li key={step} className="flex items-start gap-3">
              <span
                aria-hidden="true"
                className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-edge text-sm font-medium text-graphite"
              >
                {index + 1}
              </span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </section>
      <StartInterviewForm />
    </div>
  );
}
