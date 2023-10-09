from multiprocessing.dummy import Pool as ThreadPool

def thread_pool(worker, arg_list: list, n_threads: int) -> list:
    pool = ThreadPool(n_threads)
    results = pool.map(worker, arg_list)
    pool.close()
    pool.join()
    return results