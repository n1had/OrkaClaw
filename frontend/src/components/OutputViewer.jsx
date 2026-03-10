import ReactMarkdown from 'react-markdown'

export default function OutputViewer({ content, streaming }) {
  return (
    <div className={`output-viewer${streaming ? ' streaming' : ''}`}>
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  )
}
