import React, { useState } from 'react';

function App() {
  const [file, setFile] = useState(null);
  const [insights, setInsights] = useState('');
  const [transactions, setTransactions] = useState([]);

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
  };

  const handleUpload = async () => {
    if (!file) {
      alert('Please select a file first!');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('http://localhost:8000/process-transactions', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      setInsights(data.insights);
      setTransactions(data.transactions);
    } catch (error) {
      console.error('Error uploading file:', error);
      alert('Upload failed.');
    }
  };

  return (
    <div style={{ padding: '20px' }}>
      <h1>AI Financial Analyzer</h1>

      <input type="file" accept=".csv" onChange={handleFileChange} />
      <button onClick={handleUpload} style={{ marginLeft: '10px' }}>Analyze</button>

      <h2>Insights:</h2>
      <p>{insights}</p>

      <h2>Transactions:</h2>
      <ul>
        {transactions.map((txn, index) => (
          <li key={index}>
            {txn.date} - {txn.description} - ${txn.amount} - {txn.category}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default App;
