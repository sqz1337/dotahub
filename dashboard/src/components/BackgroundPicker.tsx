import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Palette } from "lucide-react";
import {
  backgroundOptions,
  getBackgroundPreference,
  saveBackgroundPreference,
  type BackgroundId,
} from "../backgrounds";

export function BackgroundPicker() {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<BackgroundId>(getBackgroundPreference);
  const pickerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;

    const closeOnPointerDown = (event: PointerEvent) => {
      if (!pickerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };

    document.addEventListener("pointerdown", closeOnPointerDown);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnPointerDown);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const chooseBackground = (background: BackgroundId) => {
    setSelected(background);
    saveBackgroundPreference(background);
    setOpen(false);
  };

  return (
    <div className="background-picker" ref={pickerRef}>
      <button
        className="background-trigger"
        type="button"
        aria-label="Choose page background"
        aria-haspopup="menu"
        aria-expanded={open}
        title="Choose background"
        onClick={() => setOpen((current) => !current)}
      >
        <Palette aria-hidden="true" />
        <ChevronDown className="background-trigger-chevron" aria-hidden="true" />
      </button>

      {open ? (
        <div className="background-menu" role="menu" aria-label="Page background">
          <span className="background-menu-title">Background</span>
          {backgroundOptions.map((option) => (
            <button
              className="background-option"
              type="button"
              role="menuitemradio"
              aria-checked={selected === option.id}
              key={option.id}
              onClick={() => chooseBackground(option.id)}
            >
              <span className={`background-preview background-preview-${option.id}`} aria-hidden="true" />
              <span>{option.label}</span>
              {selected === option.id ? <Check aria-hidden="true" /> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
