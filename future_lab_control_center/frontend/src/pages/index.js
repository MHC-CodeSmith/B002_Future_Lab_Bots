import React from 'react';

export default function Home() {
  return (
    <div style={{ padding: '2rem', fontFamily: 'sans-serif' }}>
      <h1>🤖 Future Lab Control Center</h1>
      <p>Painel de Controle Unificado da Célula (MyCobot 280 + TurtleBot 4)</p>
      <div style={{ marginTop: '1rem', padding: '1rem', background: '#f0f4f8', borderRadius: '8px' }}>
        <strong>Status da API:</strong> Aguardando conexão...
      </div>
    </div>
  );
}
