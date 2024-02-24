#!/bin/bash
source /home/jhsia2/.bashrc
conda activate py10

export PYTHONPATH=$PYTHONPATH:/home/jhsia2/ragged


retrievers=("colbert" "bm25" "gold")
datasets=("nq" "hotpotqa" "bioasq")

# Loop through each retriever
for retriever in "${retrievers[@]}"; do
    for dataset in "${datasets[@]}"; do
        python evaluate_retriever.py --retriever $retriever --dataset $dataset --data_dir --evaluation_dir --prediction_dir
    done
done 