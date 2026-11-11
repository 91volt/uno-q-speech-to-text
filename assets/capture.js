class Capture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunk = new Float32Array(Math.round(sampleRate / 10));
    this.offset = 0;
    this.port.onmessage = ({ data }) => {
      if (data === "flush") {
        if (this.offset)
          this.port.postMessage(this.chunk.slice(0, this.offset));
        this.offset = 0;
        this.port.postMessage("flushed");
      }
    };
  }
  process(inputs) {
    const channels = inputs[0];
    if (!channels?.length) return true;
    for (let i = 0; i < channels[0].length; i++) {
      let v = 0;
      for (const channel of channels) v += channel[i] / channels.length;
      this.chunk[this.offset++] = v;
      if (this.offset === this.chunk.length) {
        this.port.postMessage(this.chunk, [this.chunk.buffer]);
        this.chunk = new Float32Array(Math.round(sampleRate / 10));
        this.offset = 0;
      }
    }
    return true;
  }
}
registerProcessor("capture", Capture);
