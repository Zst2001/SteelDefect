"""Cross-page classification boundaries; only run with the offline runner."""
from test_classification_backend import cls, create
from test_phase_a_authorization import lab
from app.db.models import Dataset, DatasetVersion
from app.errors import AppError
from app.services.datasets import list_dataset_catalog, dataset_detail_payload
from app.util_time import new_id
import pytest


def test_classification_batches_do_not_look_like_empty_segmentation_datasets(cls):
    db, owner = cls.lab.db, cls.lab.owner
    batch, _ = create(cls)
    version = db.get(DatasetVersion, batch["batch_id"])
    dataset_id = version.dataset_id
    empty = Dataset(id=new_id(), owner_id=owner.id, name="unpopulated preset", visibility="preset")
    db.add(empty)
    db.commit()
    rows = list_dataset_catalog(db, owner)["items"]
    assert dataset_id not in {row["id"] for row in rows}
    assert empty.id in {row["id"] for row in rows}
    assert cls.lab.batch.dataset_id in {row["id"] for row in rows}
    with pytest.raises(AppError) as error:
        dataset_detail_payload(db, owner, dataset_id)
    assert error.value.status_code == 404
