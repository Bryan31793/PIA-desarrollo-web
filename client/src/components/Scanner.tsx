import { useEffect, useRef, useState } from 'react';
import type { IScannerControls } from '@zxing/browser';
import { Button, Icon, Notice } from './ui';

export function Scanner({
  onScan,
  disabled,
}: {
  onScan: (value: string) => void;
  disabled: boolean;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [running, setRunning] = useState(false);
  const [readingFile, setReadingFile] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onScanRef = useRef(onScan);
  onScanRef.current = onScan;
  useEffect(() => {
    if (!running || !video.current) return;
    let cancelled = false;
    let found = false;
    let controls: IScannerControls | undefined;
    const element = video.current;
    void import('@zxing/browser')
      .then(async ({ BrowserQRCodeReader }) => {
        if (cancelled) return;
        const reader = new BrowserQRCodeReader();
        controls = await reader.decodeFromConstraints(
          { video: { facingMode: { ideal: 'environment' } }, audio: false },
          element,
          (result, _error, activeControls) => {
            if (!result || found || cancelled) return;
            found = true;
            activeControls.stop();
            setRunning(false);
            onScanRef.current(result.getText());
          },
        );
        if (cancelled || found) controls.stop();
      })
      .catch(() => {
        if (!cancelled) {
          setRunning(false);
          setError(
            'No se pudo abrir la cámara. Permite su acceso o carga una imagen del QR. La cámara necesita HTTPS o localhost.',
          );
        }
      });
    return () => {
      cancelled = true;
      controls?.stop();
      const stream = element.srcObject;
      if (stream instanceof MediaStream) stream.getTracks().forEach((track) => track.stop());
      element.srcObject = null;
    };
  }, [running]);
  useEffect(() => {
    if (disabled) setRunning(false);
  }, [disabled]);
  const readFile = async (file: File) => {
    setRunning(false);
    setError(null);
    setReadingFile(true);
    const url = URL.createObjectURL(file);
    try {
      const { BrowserQRCodeReader } = await import('@zxing/browser');
      const result = await new BrowserQRCodeReader().decodeFromImageUrl(url);
      onScanRef.current(result.getText());
    } catch {
      setError('No encontramos un QR legible en esa imagen. Intenta con otra.');
    } finally {
      URL.revokeObjectURL(url);
      setReadingFile(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  };
  return (
    <div className="scanner">
      <div className={`scanner-view ${running ? 'running' : ''}`}>
        <video ref={video} autoPlay muted playsInline aria-label="Cámara para leer el QR" />
        {!running && (
          <div className="scanner-placeholder">
            <span className="scanner-corners">
              <Icon name="scan" size={62} />
            </span>
            <strong>Todo listo para recibirlos</strong>
            <p>Coloca el QR del miembro frente a la cámara.</p>
          </div>
        )}
        {running && <span className="scan-line" aria-hidden="true" />}
      </div>
      <Notice>{error}</Notice>
      <div className="button-row">
        <Button
          disabled={disabled || readingFile}
          onClick={() => {
            setError(null);
            setRunning(!running);
          }}
        >
          <Icon name="scan" size={18} />
          {running ? 'Detener cámara' : 'Abrir cámara'}
        </Button>
        <Button
          variant="secondary"
          busy={readingFile}
          disabled={disabled}
          onClick={() => fileInput.current?.click()}
        >
          Cargar imagen QR
        </Button>
      </div>
      <input
        ref={fileInput}
        type="file"
        accept="image/*"
        className="visually-hidden"
        aria-label="Imagen del QR"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void readFile(file);
        }}
      />
    </div>
  );
}
