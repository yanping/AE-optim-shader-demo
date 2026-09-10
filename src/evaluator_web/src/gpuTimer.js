// EXT_disjoint_timer_query_webgl2 Hardware GPU Timing Helper

export class GPUTimer {
  constructor(gl) {
    this.gl = gl;
    this.ext = gl.getExtension('EXT_disjoint_timer_query_webgl2');
    this.isSupported = !!this.ext;
  }

  createQuery() {
    if (!this.isSupported) return null;
    return this.gl.createQuery();
  }

  beginQuery(query) {
    if (!this.isSupported || !query) return;
    this.gl.beginQuery(this.ext.TIME_ELAPSED_EXT, query);
  }

  endQuery(query) {
    if (!this.isSupported || !query) return;
    this.gl.endQuery(this.ext.TIME_ELAPSED_EXT);
  }

  async pollResult(query) {
    if (!this.isSupported || !query) return null;
    const gl = this.gl;
    const ext = this.ext;

    return new Promise((resolve) => {
      let attempts = 0;
      const maxAttempts = 200;

      const check = () => {
        attempts++;
        const available = gl.getQueryParameter(query, gl.QUERY_RESULT_AVAILABLE);
        const disjoint = gl.getParameter(ext.GPU_DISJOINT_EXT);

        if (disjoint) {
          gl.deleteQuery(query);
          resolve(null);
          return;
        }

        if (available) {
          const timeNs = gl.getQueryParameter(query, gl.QUERY_RESULT);
          gl.deleteQuery(query);
          resolve(timeNs / 1e6); // Convert nanoseconds to milliseconds
        } else if (attempts >= maxAttempts) {
          gl.deleteQuery(query);
          resolve(null);
        } else {
          setTimeout(check, 1);
        }
      };
      check();
    });
  }
}
