import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Typography,
  Card,
  Button,
  Tag,
  Space,
  Descriptions,
  Progress,
  App,
  Form,
  Input,
  InputNumber,
} from 'antd';
import {
  PlayCircleOutlined,
  ExperimentOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { getTrainingRuns, createTrainingRun } from '../lib/api';
import PageSkeleton from '../components/shared/PageSkeleton';
import FormModal from '../components/shared/FormModal';
import dayjs from 'dayjs';

const statusConfig: Record<string, { color: string; icon: any }> = {
  pending: { color: 'default', icon: <ClockCircleOutlined /> },
  running: { color: 'processing', icon: <LoadingOutlined spin /> },
  completed: { color: 'success', icon: <CheckCircleOutlined /> },
  failed: { color: 'error', icon: <CloseCircleOutlined /> },
};

export default function Training() {
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const queryClient = useQueryClient();

  // React Query replaces useEffect + setInterval — no clearInterval needed
  const { data: runs = [], isLoading } = useQuery<any[]>({
    queryKey: ['trainingRuns'],
    queryFn: async () => {
      const d = await getTrainingRuns();
      return d.data ?? [];
    },
    refetchInterval: 10_000,
  });

  const createMutation = useMutation({
    mutationFn: createTrainingRun,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trainingRuns'] });
      message.success('Training run started');
      setModalOpen(false);
      form.resetFields();
    },
  });

  if (isLoading) return <PageSkeleton />;

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <Typography.Title level={4} style={{ margin: 0 }}>
          Training
        </Typography.Title>
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          onClick={() => setModalOpen(true)}
        >
          New Training Run
        </Button>
      </div>

      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {runs.length === 0 ? (
          <Card style={{ textAlign: 'center', padding: 48 }}>
            <ExperimentOutlined style={{ fontSize: 48, color: '#4b5563' }} />
            <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
              No training runs yet
            </Typography.Paragraph>
            <Button type="primary" onClick={() => setModalOpen(true)}>
              Start Your First Training Run
            </Button>
          </Card>
        ) : (
          runs.map((run) => {
            const sc = statusConfig[run.status] || statusConfig.pending;
            return (
              <Card key={run.id} size="small">
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 12,
                  }}
                >
                  <Space>
                    <ExperimentOutlined style={{ color: '#8b5cf6' }} />
                    <Typography.Text strong style={{ fontFamily: 'monospace' }}>
                      {run.id.slice(0, 8)}
                    </Typography.Text>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {run.base_model}
                    </Typography.Text>
                  </Space>
                  <Tag icon={sc.icon} color={sc.color}>
                    {run.status}
                  </Tag>
                </div>

                {run.status === 'running' && (
                  <Progress percent={50} status="active" size="small" style={{ marginBottom: 12 }} />
                )}

                <Descriptions size="small" column={{ xs: 1, sm: 2, md: 4 }}>
                  <Descriptions.Item label="Dataset">{run.dataset_size} samples</Descriptions.Item>
                  <Descriptions.Item label="Config">
                    rank={run.config?.lora_rank} epochs={run.config?.epochs}
                  </Descriptions.Item>
                  <Descriptions.Item label="Started">
                    {run.started_at ? dayjs(run.started_at).format('MM-DD HH:mm') : '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Completed">
                    {run.completed_at ? dayjs(run.completed_at).format('MM-DD HH:mm') : '—'}
                  </Descriptions.Item>
                </Descriptions>

                {run.metrics && (
                  <Card size="small" style={{ marginTop: 12 }} type="inner" title="Evaluation Results">
                    <Descriptions size="small" column={3}>
                      <Descriptions.Item label="Base Loss">
                        {run.metrics.avg_base_loss}
                      </Descriptions.Item>
                      <Descriptions.Item label="Fine-tuned Loss">
                        {run.metrics.avg_finetuned_loss}
                      </Descriptions.Item>
                      <Descriptions.Item label="Improvement">
                        <Typography.Text type={run.metrics.improved ? 'success' : 'danger'}>
                          {(run.metrics.improvement * 100).toFixed(1)}%
                        </Typography.Text>
                      </Descriptions.Item>
                    </Descriptions>
                  </Card>
                )}

                {run.ollama_model && (
                  <Tag color="success" style={{ marginTop: 8 }}>
                    Deployed: {run.ollama_model}
                  </Tag>
                )}
              </Card>
            );
          })
        )}
      </Space>

      <FormModal
        title="New Training Run"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onSubmit={(values) => createMutation.mutateAsync(values)}
        okText="Start Training"
        form={form}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ base_model: 'mistralai/Mistral-7B-Instruct-v0.3', lora_rank: 16, epochs: 3 }}
        >
          <Form.Item name="base_model" label="Base Model" rules={[{ required: true }]}>
            <Input
              placeholder="mistralai/Mistral-7B-Instruct-v0.3"
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
          <Space>
            <Form.Item name="lora_rank" label="LoRA Rank">
              <InputNumber min={4} max={128} />
            </Form.Item>
            <Form.Item name="epochs" label="Epochs">
              <InputNumber min={1} max={20} />
            </Form.Item>
          </Space>
        </Form>
      </FormModal>
    </div>
  );
}
