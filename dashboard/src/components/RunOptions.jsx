export default function RunOptions({ options, onChange, capabilities, disabled = false }) {
  const modelEnabled = options.quality_signal === "model";
  const gpuUnavailable = capabilities?.cuda_available === false;

  return (
    <div className="run-options">
      <label className="run-option">
        <span>Quality labels</span>
        <select
          value={options.quality_signal}
          disabled={disabled}
          onChange={(event) => onChange({
            ...options,
            quality_signal: event.target.value,
            device: event.target.value === "off" ? "auto" : options.device,
          })}
        >
          <option value="off">Off — standard run (default)</option>
          <option value="model">On — add model labels</option>
        </select>
      </label>

      <label className="run-option">
        <span>Model device</span>
        <select
          value={options.device}
          disabled={disabled || !modelEnabled}
          onChange={(event) => onChange({ ...options, device: event.target.value })}
        >
          <option value="auto">Auto (default)</option>
          <option value="cpu">CPU</option>
          <option value="cuda" disabled={gpuUnavailable}>GPU (CUDA)</option>
        </select>
      </label>

      <p className="cell-sub run-option-help">
        {!modelEnabled
          ? "Standard run: regex + spaCy PII, no quality model. Turn on labels to choose a model device."
          : gpuUnavailable
            ? "No CUDA GPU is available to this server. Auto will use the CPU."
            : capabilities?.gpu_name
              ? `GPU available: ${capabilities.gpu_name}. Auto uses it when available.`
              : "Auto checks this server for a CUDA GPU. GPU requires CUDA-enabled PyTorch."}
        {" "}PII always uses regex + spaCy.
      </p>
    </div>
  );
}
