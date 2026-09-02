import { Card, CardHeader, CardBody } from '@/components/ui/Card';

/** Standard wrapper for chart panels. */
export function ChartCard({ title, subtitle, actions, children, className, bodyClassName }) {
  return (
    <Card className={className}>
      {(title || actions) && <CardHeader title={title} subtitle={subtitle} actions={actions} />}
      <CardBody className={bodyClassName}>{children}</CardBody>
    </Card>
  );
}
