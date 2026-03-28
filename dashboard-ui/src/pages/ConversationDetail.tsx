import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Card, Tag, Button, Descriptions, Typography, Space, App, Tooltip, Result, Collapse } from 'antd';
import {
  ArrowLeftOutlined,
  LikeOutlined,
  DislikeOutlined,
  UserOutlined,
  RobotOutlined,
  ToolOutlined,
  CopyOutlined,
  CodeOutlined,
} from '@ant-design/icons';
import { getConversation, addFeedback } from '../lib/api';
import PageSkeleton from '../components/shared/PageSkeleton';
import dayjs from 'dayjs';

const { Text } = Typography;

const roleConfig: Record<string, { icon: any; color: string; border: string }> = {
  user: { icon: <UserOutlined />, color: '#3b82f6', border: '#3b82f620' },
  assistant: { icon: <RobotOutlined />, color: '#8b5cf6', border: '#8b5cf620' },
  system: { icon: <ToolOutlined />, color: '#6b7280', border: '#6b728020' },
  tool: { icon: <ToolOutlined />, color: '#f59e0b', border: '#f59e0b20' },
};

export default function ConversationDetail() {
  const { id } = useParams();
  const [conv, setConv] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const { message: messageApi } = App.useApp();

  useEffect(() => {
    if (id) {
      getConversation(id).then(setConv).catch(() => {}).finally(() => setLoading(false));
    }
  }, [id]);

  if (loading) return <PageSkeleton type="detail" />;

  if (!conv) {
    return (
      <Result
        status="404"
        title="Conversation Not Found"
        subTitle="This conversation does not exist or has been removed."
        extra={
          <Link to="/conversations">
            <Button icon={<ArrowLeftOutlined />}>Back to Conversations</Button>
          </Link>
        }
      />
    );
  }

  const handleFeedback = async (messageId: string, value: number) => {
    await addFeedback(conv.id, messageId, value);
    messageApi.success('Feedback recorded');
  };

  const copyMessage = (content: string) => {
    navigator.clipboard.writeText(content);
    messageApi.success('Copied to clipboard');
  };

  const hasTotals = conv.total_prompt_tokens || conv.total_completion_tokens || conv.total_cost_usd;
  const hasMetadata = conv.metadata && Object.keys(conv.metadata).length > 0;

  return (
    <div style={{ maxWidth: 900 }}>
      <Space style={{ marginBottom: 16 }}>
        <Link to="/conversations">
          <Button icon={<ArrowLeftOutlined />}>Back</Button>
        </Link>
        <Typography.Title level={4} style={{ margin: 0 }}>Conversation</Typography.Title>
        <Tag color="purple">{conv.source}</Tag>
      </Space>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Descriptions column={{ xs: 1, sm: 2, md: 3 }} size="small">
          <Descriptions.Item label="ID">
            <Text copyable style={{ fontFamily: 'monospace', fontSize: 12 }}>{conv.id}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="User">{conv.user_id || '—'}</Descriptions.Item>
          <Descriptions.Item label="Created">
            {conv.created_at ? dayjs(conv.created_at).format('YYYY-MM-DD HH:mm:ss') : '—'}
          </Descriptions.Item>
          <Descriptions.Item label="Messages">{conv.messages?.length ?? 0}</Descriptions.Item>
          {hasTotals && (
            <>
              <Descriptions.Item label="Total Tokens">
                <Text style={{ fontSize: 12 }}>
                  {conv.total_prompt_tokens}+{conv.total_completion_tokens}
                  <Text type="secondary" style={{ fontSize: 11 }}> ({(conv.total_prompt_tokens + conv.total_completion_tokens).toLocaleString()} total)</Text>
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label="Total Cost">
                <Text style={{ fontSize: 12 }}>${conv.total_cost_usd?.toFixed(4)}</Text>
              </Descriptions.Item>
            </>
          )}
        </Descriptions>

        {hasMetadata && (
          <Collapse
            ghost
            size="small"
            style={{ marginTop: 8 }}
            items={[{
              key: 'meta',
              label: <Space><CodeOutlined /><Text type="secondary" style={{ fontSize: 11 }}>Metadata</Text></Space>,
              children: (
                <pre style={{ fontSize: 11, margin: 0, padding: 8, background: 'rgba(0,0,0,0.15)', borderRadius: 4, overflowX: 'auto' }}>
                  {JSON.stringify(conv.metadata, null, 2)}
                </pre>
              ),
            }]}
          />
        )}
      </Card>

      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        {(conv.messages ?? []).map((msg: any) => {
          const config = roleConfig[msg.role] || roleConfig.user;
          return (
            <Card
              key={msg.id}
              size="small"
              style={{ borderLeft: `3px solid ${config.color}` }}
              title={
                <Space>
                  {config.icon}
                  <Text strong style={{ textTransform: 'capitalize' }}>{msg.role}</Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>#{msg.sequence}</Text>
                  {msg.token_count && <Text type="secondary" style={{ fontSize: 11 }}>{msg.token_count} tokens</Text>}
                </Space>
              }
              extra={
                <Space>
                  <Tooltip title="Copy">
                    <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => copyMessage(msg.content)} />
                  </Tooltip>
                  {msg.role === 'assistant' && (
                    <>
                      <Tooltip title="Good response">
                        <Button type="text" size="small" icon={<LikeOutlined />} onClick={() => handleFeedback(msg.id, 1.0)} />
                      </Tooltip>
                      <Tooltip title="Bad response">
                        <Button type="text" size="small" icon={<DislikeOutlined />} onClick={() => handleFeedback(msg.id, 0.0)} />
                      </Tooltip>
                    </>
                  )}
                </Space>
              }
            >
              <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 13 }}>
                {msg.content}
              </div>

              {msg.routing_decision && (
                <div style={{ marginTop: 12, padding: 8, background: 'rgba(0,0,0,0.1)', borderRadius: 6 }}>
                  <Space wrap size={4}>
                    <Tag color="blue">{msg.routing_decision.provider}</Tag>
                    <Tag color="purple">{msg.routing_decision.model}</Tag>
                    <Tag color="gold">{msg.routing_decision.task_type}</Tag>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {msg.routing_decision.latency_ms}ms · ${msg.routing_decision.cost_usd?.toFixed(4)} · {msg.routing_decision.prompt_tokens}+{msg.routing_decision.completion_tokens} tokens
                    </Text>
                  </Space>
                </div>
              )}

              {msg.quality_signals?.length > 0 && (
                <Space style={{ marginTop: 8 }}>
                  {msg.quality_signals.map((s: any, i: number) => (
                    <Tag key={i} color={s.value >= 0.5 ? 'success' : 'error'}>
                      {s.type}: {s.value}
                    </Tag>
                  ))}
                </Space>
              )}
            </Card>
          );
        })}
      </Space>
    </div>
  );
}
