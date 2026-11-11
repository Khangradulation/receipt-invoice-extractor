import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Modal } from '@/components/ui';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';

/** Permanently deletes a document (file, extracted data and analytics rows) after confirmation. */
export function DeleteDocumentButton({
  documentId,
  filename,
}: {
  documentId: string;
  filename: string;
}) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: () => api.deleteDocument(documentId),
    onSuccess: async () => {
      setOpen(false);
      queryClient.removeQueries({ queryKey: ['document', documentId] });
      queryClient.removeQueries({ queryKey: ['file-url', documentId] });
      await queryClient.invalidateQueries();
      navigate('/documents', { replace: true });
    },
  });
  const close = () => {
    if (!remove.isPending) {
      setOpen(false);
      remove.reset();
    }
  };
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <Trash2 className="size-4" aria-hidden="true" /> Delete
      </Button>
      <Modal
        open={open}
        title="Delete document"
        onClose={close}
        footer={
          <>
            <Button variant="secondary" onClick={close} disabled={remove.isPending}>
              Cancel
            </Button>
            <Button variant="danger" onClick={() => remove.mutate()} disabled={remove.isPending}>
              {remove.isPending ? 'Deleting…' : 'Delete permanently'}
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-600">
          <span className="font-medium text-slate-900">{filename}</span>, its extracted data and its
          analytics records will be permanently deleted. This can’t be undone.
        </p>
        {remove.isError && (
          <div className="mt-3">
            <Alert tone="error" title="Couldn’t delete">
              {errorMessage(remove.error)}
            </Alert>
          </div>
        )}
      </Modal>
    </>
  );
}
