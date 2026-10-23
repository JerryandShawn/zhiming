import { useState } from 'react';
import { Button, Input } from '../../components/ui/Controls';

// Legacy v3 clarification continues its original run. v4 AskCard starts a new turn.
export function ClarificationCard({ questions, onReply }: { questions: string[]; onReply: (answer: string) => void }) {
  const [reply, setReply] = useState('');
  return (
    <form
      className="ask-card"
      onSubmit={(event) => {
        event.preventDefault();
        if (reply.trim()) onReply(reply.trim());
      }}>
      {questions.map((question) => (
        <p key={question}>{question}</p>
      ))}
      <label>
        补充本轮澄清信息
        <Input value={reply} onChange={(event) => setReply(event.target.value)} />
      </label>
      <Button type="submit" disabled={!reply.trim()}>
        补充并继续
      </Button>
    </form>
  );
}
