import axios from 'axios';
import { useState } from 'react';
import './App.css';
import { ProcessResponse } from './types';

function App() {
  const [link, setLink] = useState<string>('');
  const [result, setResult] = useState<ProcessResponse | null>(null);
  const [error, setError] = useState<string>('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setResult(null);

    try {
      const response = await axios.post<ProcessResponse>('http://localhost:8000/process-link', {
        url: link,
      });
      setResult(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'An error occurred');
    }
  };

  return (
    <div className="App">
      <h1>YouTube Music Link Processor</h1>
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={link}
          onChange={(e) => setLink(e.target.value)}
          placeholder="Paste YouTube Music link"
          style={{ width: '300px', padding: '10px' }}
        />
        <button type="submit">Process</button>
      </form>

      {error && <p style={{ color: 'red' }}>{error}</p>}

      {result && (
        <div>
          <h2>Track Info</h2>
          <p><strong>Title:</strong> {result.metadata.title}</p>
          <p><strong>Channel:</strong> {result.metadata.channel}</p>
          {result.metadata.duration && <p><strong>Duration:</strong> {result.metadata.duration}</p>}
          {result.metadata.thumbnail && <img src={result.metadata.thumbnail} alt="Thumbnail" />}
          {result.download_url ? (
            <div>
              <p><strong>Download:</strong></p>
              <a href={result.download_url} download>
                Download MP3
              </a>
            </div>
          ) : (
            <p>No download available (legal restrictions)</p>
          )}
        </div>
      )}
    </div>
  );
}

export default App;