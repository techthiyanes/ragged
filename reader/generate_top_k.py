#file to generate the results of the QA taking retrival file as input

from reader.flanT5.flan_reader import FlanReader
import argparse
import os
import time
import traceback

from tqdm import tqdm
from file_utils import BASE_FOLDER, NOISY_READER_BASE_FOLDER, ONLY_GOLD_READER_BASE_FOLDER, READER_BASE_FOLDER, save_jsonl, load_jsonl, save_json
from reader.llama2.llama2_reader import LlamaReader

time_map = {}


def post_process_answers(answers):
    return [x.strip().split("\n")[0] for x in answers]

def generate_reader_outputs(input_path, reader_object, output_path=None, start_offset=0, end_offset=None, top_k=1, args=None):
    
    batch_size = 50
    output_file = f'{output_path}reader_output_index_{args.start_offset}_to_{args.end_offset}.jsonl'
    retriever_data = load_jsonl(input_path)
    reader_responses = load_jsonl(output_file) if os.path.exists(output_file) else []
    print(f"no.of. questions in range {start_offset} to {end_offset} for which response is already generated = {len(reader_responses)}")

    error_file_path = output_file[:-6]+"_errors.jsonl"
    error_logs = load_jsonl(error_file_path, sort_by_id=False) if os.path.exists(error_file_path) else []

    reader_ques_ids_already_generated = [x['id'] for x in reader_responses] #can modify this to combined_jsonl file

    if not end_offset:
        end_offset = len(retriever_data)
    end_offset = min(end_offset, len(retriever_data))

    all_prompts = []
    prompt_indices = []
    time1 = time.time()
    for i, ques_info in tqdm(enumerate(retriever_data[start_offset:end_offset])):
        if ((start_offset + i)%1000==0):
            print("index : ", start_offset+i)

        if ques_info["id"] in reader_ques_ids_already_generated:
            continue

        question = ques_info["input"]+"?"
        relevant_documents = ques_info["output"][0]["provenance"]
        if args.non_gold:
            match_term = "wiki_par_id_match" if args.dataset in ["nq", "hotpotqa"] else "pm_sec_id_match"
            relevant_documents = [r for r in relevant_documents if r[match_term]==False]
        elif args.only_gold:
            match_term = "wiki_par_id_match" if args.dataset in ["nq", "hotpotqa"] else "pm_sec_id_match"
            relevant_documents = [r for r in relevant_documents if r[match_term]==True]

        if top_k:
            retrieved_passages = relevant_documents[:top_k]
            context = "\n".join([passage["text"] for passage in retrieved_passages])
        else:
            context = ""
        
        prompt = {"question" : question, "context": context}
        all_prompts.append(prompt)
        prompt_indices.append(i)
            
    
    chunks = [list(zip(prompt_indices, all_prompts))[x:x+batch_size] for x in range(0, len(all_prompts), batch_size)]
    all_answers = []
    all_context_length_changes = []
    for chunkid, chunk in enumerate(chunks):
        print(f'{chunkid}/{len(chunks)}')
        chunk_prompts = [prompt for _, prompt in chunk]
        try:
            answers, context_length_changes = reader_object.generate(chunk_prompts, max_new_tokens=args.max_new_tokens, truncate=args.max_truncation)
            all_context_length_changes.extend(context_length_changes)
            # print(answers)
            answers = post_process_answers(answers)
            all_answers.extend(answers)
            chunk_prompt_indices = [x[0] for x in chunk]
            for q_index, answer in zip(chunk_prompt_indices, answers):
                ques_info = retriever_data[start_offset:end_offset][q_index]
                reader_responses.append({
                    "id" : ques_info["id"],
            "input" : ques_info["input"],
            "retrieved_passages": relevant_documents[:top_k],
            "answer": answer
                })
                

        except Exception:
            print(f"Exception in {chunkid} chunk")
            print(traceback.format_exc())

            error_logs.append(
                {
                    "chunk_id" : chunkid,
                    "error": traceback.format_exc()
                }
            )
            save_jsonl(error_logs, error_file_path)
        save_jsonl(reader_responses, output_file)

    time2 = time.time()
    time_map["complete_generation"] = time2-time1
    print("Total reader_responses : ", len(reader_responses))
    print("Time taken: ", time_map["complete_generation"])
    save_jsonl(reader_responses, output_file)
    save_json(all_context_length_changes, f"{output_path}reader_output_index_{args.start_offset}_to_{args.end_offset}_context_length_changes.json")
            

    

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hosted_api_path", type=str, default="babel-1-23")
    parser.add_argument("--hosted_api_port", type=str, default="9426")
    parser.add_argument("--start_offset", type=int, default=0)
    parser.add_argument("--end_offset", type=int, default=None)
    parser.add_argument("--top_k", type=int, default=1)
    parser.add_argument("--model", type=str)
    parser.add_argument("--retriever", type=str)
    parser.add_argument("--dataset", type=str)
    parser.add_argument("--max_new_tokens", type=int)
    parser.add_argument("--max_truncation", type=int, default=4000)
    parser.add_argument("--only_gold", action='store_true')
    parser.add_argument("--non_gold", action='store_true')

    args = parser.parse_args()
    print(f"args: {vars(args)}")
    return args

if __name__ == "__main__":
    args = get_args()

    model_class_dict = {
        "llama_70b" : LlamaReader,
        "flanT5" : FlanReader,
        "flanUl2" : FlanReader,
        "llama_7b": LlamaReader,
        "llama_7b_256_tokens": LlamaReader,
        "llama_70b_256_tokens": LlamaReader,
        "llama_70b_2000_truncation": LlamaReader,
        "llama_7b_2000_truncation" : LlamaReader,
        "llama_7b_256_tokens":LlamaReader,
        "flanUl2_265_tokens":FlanReader,
        "llama_7b_2000_truncation_v2": LlamaReader
    }

    retriever_path_map = {
        "bm25": f"{BASE_FOLDER}/retriever_results/predictions/bm25/",
        "colbert": f"{BASE_FOLDER}/retriever_results/predictions/colbert/"

    }

    dataset_map = {
        "hotpotqa" : "hotpotqa-dev-kilt.jsonl",
        "nq": "nq-dev-kilt.jsonl",
        "bioasq": "bioasq.jsonl",
        "complete_bioasq": "complete_bioasq.jsonl"
    }

    reader=model_class_dict[args.model](hosted_api_path =f"http://{args.hosted_api_path}:{args.hosted_api_port}/")
    
    retriever_data_path = f"{retriever_path_map[args.retriever]}{dataset_map[args.dataset]}"

    # output_path = f"/data/user_data/afreens/kilt/{args.model}/{args.dataset}/{args.retriever}/top{args.top_k}/"
    if args.non_gold:
        reader_base_folder = NOISY_READER_BASE_FOLDER
    elif args.only_gold:
        reader_base_folder = ONLY_GOLD_READER_BASE_FOLDER
    else:
        reader_base_folder = READER_BASE_FOLDER
    output_path = f"{reader_base_folder}/{args.model}/{args.dataset}/{args.retriever}/{'baseline' if args.top_k==0 else 'top'+str(args.top_k) }/"
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    output_file = f'{output_path}reader_output_index_{args.start_offset}_to_{args.end_offset}.jsonl'
    
    generate_reader_outputs(retriever_data_path, reader, output_path=output_path, start_offset=args.start_offset, end_offset=args.end_offset, top_k=args.top_k, args=args)

    print("DONE!")