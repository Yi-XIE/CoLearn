import MemorySection from "@/components/space/MemorySection";

export default function MemoryPage() {
  return (
    <div className="h-full overflow-y-auto bg-[var(--background)]">
      <div className="mx-auto w-full max-w-6xl px-6 py-6 lg:px-8">
        <MemorySection />
      </div>
    </div>
  );
}
